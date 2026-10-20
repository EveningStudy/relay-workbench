"""Guided physical test; unique evidence per camera/outage, never synthetic PASS."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import threading
import psutil
from p2.bus import Subscriber
from p2.clock import now_ns
from p2.io.live_capture import cameras


def measure_outage(rows, offline_ns, reconnect_ns):
    """Actual surrounding frames, including the pre-prompt frame.

    No recovered frame means an unbounded outage, NOT a small measured gap.
    Require a confirmed >=2s frame silence before requesting restoration.
    """
    before = [r for r in rows if r['t_recv_ns'] <= offline_ns]
    after = [r for r in rows if r['t_recv_ns'] > offline_ns]
    last = before[-1] if before else None
    first = after[0] if after else None
    silence = (offline_ns - last['t_recv_ns']) / 1e9 if last else 0
    recovered = bool(last and first and first['t_recv_ns'] >= reconnect_ns and silence >= 2)
    return {'recovered': recovered, 'offline_silence_s': silence,
            'last_frame_before_outage': last, 'first_frame_after_outage': first,
            'outage_gap_s': ((first['t_capture_ns'] - last['t_capture_ns']) / 1e9 if recovered else None),
            'ingest_gap_s': ((first['t_recv_ns'] - last['t_recv_ns']) / 1e9 if recovered else None),
            'outage_definition': 'Last host read-complete before outage to first host read-complete after recovery; not exposure timestamps.'}


def stop_tree(proc):
    try:
        children = psutil.Process(proc.pid).children(recursive=True)
    except psutil.Error:
        children = []
    # Stop the retry supervisor first, or it can spawn a replacement while its
    # old capture child is being terminated.
    if proc.poll() is None:proc.terminate()
    for child in reversed(children):
        try:child.terminate()
        except psutil.Error:pass
    proc.wait(timeout=10)
    _, alive = psutil.wait_procs(children, timeout=3)
    for child in alive:
        try:child.kill()
        except psutil.Error:pass


def ui_listening(url='http://127.0.0.1:8090', timeout=1.0):
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status == 200
    except OSError:
        return False


def wait_for_children(processes, logs, timeout_s=30, probe=ui_listening, sleep=None):
    """Fail loudly if the UI or camera publisher dies, instead of waiting at a prompt."""
    import time
    sleep = sleep or time.sleep
    deadline = time.monotonic() + timeout_s
    while True:
        for proc, log in zip(processes, logs):
            if proc.poll() is not None:
                tail = Path(log).read_text(errors='replace').splitlines()[-15:] if Path(log).exists() else []
                raise RuntimeError(f'{Path(log).stem} exited with code {proc.returncode} before the test started:\n' + '\n'.join(tail))
        if probe():
            return
        if time.monotonic() > deadline:
            raise RuntimeError('Operator UI did not serve http://127.0.0.1:8090 within %ds' % timeout_s)
        sleep(0.5)


def main():
    p=argparse.ArgumentParser();p.add_argument('--list',action='store_true')
    p.add_argument('--outage',choices=['device-manager','droidcam-stop-start','unplug'],default='device-manager')
    a=p.parse_args()
    found=cameras()
    for number,row in enumerate(found):
        print(f"[{number}] {row['name']} | {row['backend']} index {row['index']} | "
              f"{'READ OK '+str(row.get('width'))+'x'+str(row.get('height')) if row['readable'] else 'NOT READABLE: '+row.get('error','')}",flush=True)
    if a.list:return
    from p2.io.frozen_build import check,fingerprint
    freeze=check(required=True);build=fingerprint()
    if not found:raise RuntimeError('No video devices enumerated. Enable/connect the desired camera.')
    number=int(input('Choose the bracketed device row (MSMF preferred), then Enter: '))
    if not 0<=number<len(found) or not found[number]['readable']:raise ValueError('Choose a READ OK row')
    selected=found[number]
    root=Path('data/realcam/live_tests')/str(now_ns());root.mkdir(parents=True,exist_ok=False)
    (root/'device.json').write_text(json.dumps(selected,indent=2))
    out=root/'result.json';rows=[];running=True;processes=[];logs=[];ready=threading.Event()
    result={'source':'real','device':selected,'outage_type':a.outage,'rows':rows,'recovered':False,'outage_gap_s':None,
            'code_hash':build['code_hash'],'config_hash':build['config_hash'],'build_hash':build['build_hash'],
            'frozen_build_hash':freeze['build_hash'],'pose_available':False,
            'latency_scope':'Host read-complete to ingest only; physical exposure/USB latency unmeasured. RGB only, no pose.'}
    def receive():
        sub=Subscriber('camera/real_phone');ready.set()
        try:
            while running:
                item=sub.recv(20)
                if item:
                    f=item[1];t=now_ns();rows.append({'t_recv_ns':t,'seq':f.seq,'t_capture_ns':f.t_capture_ns,'age_ms':(t-f.t_capture_ns)/1e6})
        finally:sub.close()
    thread=threading.Thread(target=receive);thread.start();ready.wait(timeout=3)
    try:
        for module,extra in [('p2.ui.operator_ui',[]),('p2.io.realcam_node',['--device-json',str(root/'device.json'),'--reconnect','--output',str(root/'publish.json')])]:
            log=(root/(module.split('.')[-1]+'.txt')).open('x');logs.append(log)
            processes.append(subprocess.Popen([sys.executable,'-u','-m',module,*extra],stdout=log,stderr=subprocess.STDOUT))
        wait_for_children(processes, [root/'operator_ui.txt', root/'realcam_node.txt'])
        import webbrowser
        webbrowser.open('http://127.0.0.1:8090')
        input('Confirm real_phone is the selected physical camera and visibly updating (RGB only). Press Enter: ')
        if not rows or (now_ns()-rows[-1]['t_recv_ns'])/1e9>2:raise RuntimeError('No current frames')
        action={'device-manager':'DISABLE the selected camera in Device Manager',
                'droidcam-stop-start':'press STOP in DroidCam', 'unplug':'UNPLUG the camera'}[a.outage]
        input(f'{action}. Leave it OFF until UI is OFFLINE for at least 3 seconds. Do NOT restore yet. Press Enter: ')
        offline=now_ns();result['offline_confirmed_ns']=offline
        if (offline-rows[-1]['t_recv_ns'])/1e9<2:raise RuntimeError('Frames did not stop. No outage demonstrated (a frozen/placeholder image is not frame loss).')
        reconnect=now_ns();result['restore_requested_ns']=reconnect
        input('Now RE-ENABLE / START / RECONNECT the SAME camera. Wait for its moving image to return, then Enter (or Enter on failure): ')
        result.update(measure_outage(list(rows),offline,reconnect))
        if not result['recovered']:raise RuntimeError('No validated recovery; failure saved. Retry a new run.')
        result['physical_image_confirmed_by_operator']=True
    except BaseException as exc:
        result['error']=repr(exc);raise
    finally:
        running=False;thread.join(timeout=2)
        result['rows']=rows;out.write_text(json.dumps(result,indent=2))
        for proc in processes:stop_tree(proc)
        for log in logs:log.close()
        print('Evidence saved: '+str(out),flush=True)
    marker=Path('human_inputs')/('06_live_webcam_'+root.name+'.done')
    marker.write_text(str(out));print('PASS: '+str(out),flush=True)


if __name__=='__main__':main()
