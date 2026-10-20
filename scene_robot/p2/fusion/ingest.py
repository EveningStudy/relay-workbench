"""Independent bounded camera queues; no camera can block another."""
from collections import deque
import threading
from p2.bus import Subscriber
from p2.clock import now_ns


class Ingest:
    def __init__(self,cameras,queue_depth=2):
        self.queues={n:deque(maxlen=queue_depth) for n in cameras}
        self.latest={};self.overflows={n:0 for n in cameras};self.states=deque(maxlen=1000)
        self.arrivals={n:deque(maxlen=240) for n in cameras}
        self.running=True;self.threads=[]
        self.cursor=0
        for n in cameras:
            t=threading.Thread(target=self._camera,args=(n,),daemon=True);t.start();self.threads.append(t)
        t=threading.Thread(target=self._state,daemon=True);t.start();self.threads.append(t)

    def _camera(self,n):
        sub=Subscriber('camera/'+n)
        while self.running:
            result=sub.recv()
            if result:
                item=(result[1],now_ns())
                self.arrivals[n].append((item[1],item[0].seq,item[0].source))
                if len(self.queues[n])==self.queues[n].maxlen:self.overflows[n]+=1
                self.queues[n].append(item);self.latest[n]=item
        sub.close()

    def _state(self):
        sub=Subscriber('state/')
        while self.running:
            result=sub.recv()
            if result:self.states.append(result[1])
        sub.close()

    def ready(self):
        names=list(self.queues);start=self.cursor
        for i in range(len(names)):
            n=names[(start+i)%len(names)];q=self.queues[n]
            for _ in range(len(q)):
                try:item=q.popleft()
                except IndexError:break
                self.cursor=(names.index(n)+1)%len(names)
                yield item

    def close(self):
        self.running=False
        for t in self.threads:t.join(timeout=1)
