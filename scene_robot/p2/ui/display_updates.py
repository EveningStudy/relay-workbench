"""Presentation-only retained nodes and bounded, immutable marker jobs."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import time
import numpy as np
from p2.ui.change_markers import box_segments


def voxel_buffer(points,colors,size,capacity=None):
    """Exact viser 1.1.1 isotropic Gaussian encoding, without Nx3x3 temporaries."""
    count=len(points);capacity=count if capacity is None else capacity
    assert capacity>=count
    buffer=np.zeros((capacity,8),np.uint32)
    buffer[:count,:3]=np.ascontiguousarray(points,dtype=np.float32).view(np.uint32)
    covariance=np.array([size**2,0,0,size**2,0,size**2],np.float16).view(np.uint32)
    buffer[:,4:7]=covariance
    rgba=np.empty((count,4),np.uint8);rgba[:,:3]=colors;rgba[:,3]=int(.85*255)
    buffer[:count,7]=rgba.view(np.uint32).ravel()
    return buffer


class MarkerWorker:
    def __init__(self,detector):
        self.detector=detector;self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='marker-display')
        self.pending=None

    def submit(self,*args):
        if self.pending is not None:return False
        # No live map/tf/GPU tensors are shared with this presentation worker.
        snapshot=tuple(x.copy() if isinstance(x,np.ndarray) else deepcopy(x) for x in args)
        def calculate():
            start=time.time_ns();rows=self.detector.update(*snapshot)
            return rows,(time.time_ns()-start)/1e6
        self.pending=self.pool.submit(calculate);return True

    def poll(self):
        if self.pending is None or not self.pending.done():return None
        result=self.pending.result();self.pending=None;return result

    def close(self):self.pool.shutdown(wait=True,cancel_futures=True)


class MarkerNodes:
    def __init__(self):self.nodes={}

    def update(self,scene,rows,visible,label_scale):
        costs={'marker_lines':0.,'marker_labels':0.,'marker_remove':0.};active=set()
        for k,row in enumerate(rows):
            key=(k,row['kind']);active.add(key);old=self.nodes.get(key)
            bounds=np.array(row['bounds']);position=bounds.mean(0);position[2]=bounds[1,2]+.025
            if old is None:
                name='/change_markers/'+str(k)+'_'+row['kind'];removed=row['kind']=='removed'
                start=time.time_ns()
                line=scene.add_line_segments(name,box_segments(bounds,removed),(255,180,65) if removed else (70,245,185),thickness=1.6,thickness_units='screen',visible=visible)
                costs['marker_lines']+=(time.time_ns()-start)/1e6;start=time.time_ns()
                label=scene.add_label(name+'/label',row['label'],position=position,font_screen_scale=label_scale,anchor='bottom-center',visible=visible)
                costs['marker_labels']+=(time.time_ns()-start)/1e6
                self.nodes[key]=(line,label,bounds)
            else:
                line,label,previous=old
                if not np.array_equal(bounds,previous):
                    start=time.time_ns();line.points=box_segments(bounds,row['kind']=='removed')
                    costs['marker_lines']+=(time.time_ns()-start)/1e6;start=time.time_ns()
                    label.position=position;costs['marker_labels']+=(time.time_ns()-start)/1e6
                    self.nodes[key]=(line,label,bounds)
                line.visible=visible;label.visible=visible
                label.font_screen_scale=label_scale
        start=time.time_ns()
        for key in set(self.nodes)-active:
            line,label,_=self.nodes.pop(key);label.remove();line.remove()
        costs['marker_remove']=(time.time_ns()-start)/1e6
        return costs
