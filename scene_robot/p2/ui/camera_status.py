"""Camera delivery health is separate from deliberate freshness queue trimming."""
def delivery_loss(history,now):
    rows=[r for r in list(history) if now-r[0]<=3_000_000_000]
    if len(rows)<3 or rows[-1][0]-rows[0][0]<2_000_000_000:return 0.
    # Saved recordings intentionally omit frames and retain original sequence IDs.
    if rows[-1][2]=='replay':return 0.
    expected=rows[-1][1]-rows[0][1]
    return max(0.,1-(len(rows)-1)/expected) if expected>0 else 0.


def state(now,received,age_ms,loss):
    return 'OFFLINE' if now-received>1_000_000_000 else ('LATE' if age_ms>250 else ('DROPPING' if loss>.2 else 'OK'))
