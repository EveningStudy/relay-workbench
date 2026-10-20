import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from eval.metrics.statistics import eer, clustered_ci, error_counts


def main():
    separated, pos, neg = eer(np.array([[1., 0], [1., 0], [0, 1.], [0, 1.]]), ["a", "a", "b", "b"])
    assert separated == 0 and pos == 2 and neg == 4
    # EER must group tied scores; a collapsed embedding offers no discrimination.
    collapsed, _, _ = eer(np.ones((4, 2)), ["a", "a", "b", "b"])
    assert abs(collapsed - 0.5) < 1e-12
    counts = error_counts("one two three", "one four three", lambda x:x)
    assert counts["word_errors"] == 1 and counts["words"] == 3
    rows = [{"speaker": s, "word_errors": 1, "words": 10} for s in ["a", "b", "c"]]
    ci = clustered_ci(rows)
    assert ci == [0.1, 0.1]
    result = {"perfectly_separated_eer": separated, "collapsed_embedding_eer": collapsed,
              "word_counts": counts, "clustered_constant_ci": ci}
    Path("results/metrics_acceptance.json").write_text(json.dumps(result, indent=2))
    print(result)


if __name__ == "__main__":
    main()
