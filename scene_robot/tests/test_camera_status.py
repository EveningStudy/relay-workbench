from p2.ui.camera_status import delivery_loss,state


def test_sustained_missing_input_is_separate_from_recording_rate_limits():
    healthy=[(i*100_000_000,i,'synthetic') for i in range(31)]
    assert delivery_loss(healthy,3_000_000_000)==0
    lost=[r for i,r in enumerate(healthy) if i%2==0]
    assert delivery_loss(lost,3_000_000_000)==.5
    assert state(3_000_000_000,3_000_000_000,20,.5)=='DROPPING'
    assert delivery_loss([(t,s,'replay') for t,s,_ in lost],3_000_000_000)==0
    assert state(3_000_000_000,3_000_000_000,20,0)=='OK'
    assert state(4_100_000_000,3_000_000_000,1100,0)=='OFFLINE'
