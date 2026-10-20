"""Application-only keyboard isolation and bounded teleop preset trajectories.

Pinned viser 1.1.1 CameraControls.tsx uses event.code; CommandPalette.tsx
uses Mantine event.key hotkeys. No public keyboard-only camera switch exists.
Keep mouse controls intact and blank code only for our robot keys, in capture
phase before either document listener. Do not patch the installed dependency.
"""
import xml.etree.ElementTree as ET


KEYBOARD_JS = r"""
(() => {
  if (window.eloTeleopKeys) return;
  window.eloTeleopKeys = true;
  const keys = new Set(['w','s','a','d','q','e','r','f','t','g',
    'arrowleft','arrowright','arrowup','arrowdown','1','2','3','4','5','6',
    '[',']','i','k','j','l','u','o',' ']);
  const base = new Set(['w','s','a','d','q','e']);
  const held = new Set();
  const form = e => e.target instanceof Element &&
    !!e.target.closest('input,textarea,select,[contenteditable="true"],[role="textbox"]');
  // Mantine ignores hotkeys whose target is not an HTMLElement (Document is
  // not one). Dispatch on body so holds refresh the existing 250 ms deadman.
  const emit = key => document.body.dispatchEvent(new KeyboardEvent('keydown',
    {key,code:'',bubbles:true,cancelable:true}));
  const clear = () => { held.clear(); emit(' '); };
  window.addEventListener('keydown', e => {
    const key=e.key.toLowerCase();
    if (!keys.has(key) || form(e) || e.ctrlKey || e.metaKey || e.altKey) return;
    // Also ignore Shift for camera navigation; command hotkeys require no Shift.
    Object.defineProperty(e,'code',{value:''});
    e.preventDefault();
    if (key===' ') held.clear();
    if (base.has(key)) {
      if (!e.shiftKey) held.add(key);
      if (e.repeat) e.stopImmediatePropagation();
    } else if (e.repeat) e.stopImmediatePropagation();
  },true);
  window.addEventListener('keyup', e => {
    const key=e.key.toLowerCase();
    if (!held.delete(key)) return;
    // A private command releases base velocity without cancelling an arm ramp.
    if (!held.size) emit('0');
    else emit(Array.from(held).at(-1));
  },true);
  setInterval(() => { if (held.size) emit(Array.from(held).at(-1)); },100);
  window.addEventListener('blur',clear);
  document.addEventListener('visibilitychange',() => { if(document.hidden) clear(); });
  document.addEventListener('pointerdown',e => {
    // Entering the panel stops motion; mouse orbit/zoom on the canvas is intact.
    if (e.target instanceof Element && e.target.closest('button,input,textarea,select')) clear();
  },true);
})();
"""


def joint_limits(path='assets/robot/relay.urdf'):
    return {j.attrib['name']: {k:float(v) for k,v in j.find('limit').attrib.items()}
            for j in ET.parse(path).getroot().findall('joint') if j.find('limit') is not None}


class PresetRamp:
    """Cubic ease with zero endpoint velocity; extend duration for large moves."""
    def __init__(self, start, target, limits):
        self.start=dict(start)
        self.target={n:max(limits[n]['lower'],min(limits[n]['upper'],v)) for n,v in target.items()}
        # Cubic smoothstep peak slope = 1.5. Reserve 30% velocity headroom
        # for sampled position commands and the existing simulator PD drive.
        self.duration=max(1.6,*(1.5*abs(v-self.start[n])/(.7*limits[n]['velocity'])
                                for n,v in self.target.items()))
        self.elapsed=0.

    def advance(self, dt):
        # A delayed UI frame must not turn into a large target jump.
        self.elapsed=min(self.duration,self.elapsed+max(0.,min(dt,.05)))
        u=self.elapsed/self.duration;s=u*u*(3-2*u)
        return {n:self.start[n]+s*(v-self.start[n]) for n,v in self.target.items()}

    @property
    def done(self):return self.elapsed>=self.duration
