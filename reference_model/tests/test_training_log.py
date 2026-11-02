from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_training_log import update_training_section


def test_refresh_preserves_other_experiments_and_manual_results(tmp_path):
    target = tmp_path/'README.md'
    before = '# Results\n## Document v2\nMeasured results stay here.\n'
    after = '\n## Manual notes\nKeep this evidence.\n'
    target.write_text(before+'<!-- TRAINING_LOG:START -->\nold\n<!-- TRAINING_LOG:END -->'+after)
    update_training_section(target, 'new training records')
    update_training_section(target, 'refreshed records')
    actual = target.read_text()
    assert actual.startswith(before) and actual.endswith(after)
    assert 'refreshed records' in actual and 'new training records' not in actual
    assert actual.count('<!-- TRAINING_LOG:START -->') == 1
    assert not (tmp_path/'TRAINING_LOG.md').exists()


def test_export_creates_one_category_guide(tmp_path):
    target = tmp_path/'README.md'
    update_training_section(target, 'records')
    assert '## Training log v1' in target.read_text()
    assert 'records' in target.read_text()


def test_bad_markers_do_not_overwrite_results(tmp_path):
    target = tmp_path/'README.md'
    original = '# Results\n<!-- TRAINING_LOG:START -->\nimportant records'
    target.write_text(original)
    with pytest.raises(ValueError):
        update_training_section(target, 'new')
    assert target.read_text() == original


def test_full_export_updates_category_guide_and_writes_csv(tmp_path):
    import json
    from export_training_log import export_log
    source = tmp_path/'baseline_v1'
    run = source/'size_16_seed_42'
    run.mkdir(parents=True)
    (run/'metrics.json').write_text(json.dumps(dict(
        image_size=16, seed=42, epochs_run=1, best_epoch=1,
        elapsed_seconds=1.0, validation=dict(accuracy=0.95))))
    (run/'config.json').write_text('{}')
    (run/'history.csv').write_text('epoch,validation_accuracy\n1,0.95\n')
    (run/'best.pt').write_bytes(b'test-fixture-checkpoint')
    destination = tmp_path/'results'
    destination.mkdir()
    guide = destination/'README.md'
    guide.write_text('# Results\nManual evidence must survive.\n')
    export_log(source, destination)
    assert 'Manual evidence must survive.' in guide.read_text()
    assert 'size_16_seed_42' in guide.read_text()
    assert (destination/'training_logs/baseline_v1/summary.csv').exists()
    assert not (destination/'TRAINING_LOG.md').exists()
