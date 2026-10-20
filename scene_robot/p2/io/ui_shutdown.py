"""Graceful launcher shutdown using the project's control-message schema."""
import time
from p2.bus import Publisher
from p2.msgs import Command
from p2.clock import now_ns


def main():
    pub=Publisher('tcp://127.0.0.1:5604')
    try:
        time.sleep(.6);pub.send('control/ui',Command(now_ns(),'shutdown',{}));time.sleep(.1)
    finally:pub.close()


if __name__=='__main__':main()
