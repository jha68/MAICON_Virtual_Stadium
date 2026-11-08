"""Assets are generated without remote data or scene truth."""
import copy
import hashlib
from pathlib import Path

import numpy as np
import pytest
import yaml

from maicon_sim.backends.bullet.asset_builder import (OBJECT_LABELS, load_resolved_assets,
    resolve_assets, synthetic_image)

pytestmark = pytest.mark.render


def test_procedural_shapes_are_distinct_without_color():
    digests = set()
    for label in OBJECT_LABELS:
        image = synthetic_image(label)
        assert image.mode == 'RGBA' and image.size == (512, 512)
        data = np.asarray(image.convert('L'))
        assert data.min() < 40 and data.max() > 230
        digests.add(hashlib.sha256(data.tobytes()).hexdigest())
    assert len(digests) == 6


def test_resolve_repeatable_and_preserves_source(tmp_path):
    source = Path('examples/assets_synthetic.yaml')
    original = source.read_bytes()
    a = resolve_assets(source, tmp_path/'first')
    b = resolve_assets(source, tmp_path/'second')
    assert a.manifest == b.manifest
    assert source.read_bytes() == original
    assert len(a.manifest['assets']) == 10
    loaded = load_resolved_assets(a.manifest_path, yaml.safe_load(original))
    assert all(loaded.path_for(x['asset_id']).is_file() for x in loaded.manifest['assets'])


def test_import_digest_failure_is_explicit(tmp_path):
    """RENDER-019: no silent missing/digest fallback."""
    manifest = yaml.safe_load(Path('examples/assets_synthetic.yaml').read_text())
    manifest['assets'][0].update(generator='import', path='missing.png', sha256='0'*64)
    with pytest.raises(ValueError, match='missing or SHA256 mismatch'):
        resolve_assets(manifest, tmp_path/'resolved', tmp_path)


def test_resolved_tamper_detected(tmp_path):
    r = resolve_assets('examples/assets_synthetic.yaml', tmp_path)
    r.path_for('object_tank').write_bytes(b'not an image')
    with pytest.raises(ValueError, match='SHA256 mismatch'):
        load_resolved_assets(r.manifest_path)


def test_split_group_leak_rejected(tmp_path):
    manifest = yaml.safe_load(Path('examples/assets_synthetic.yaml').read_text())
    manifest['assets'][1]['split_group'] = manifest['assets'][0]['split_group']
    manifest['assets'][1]['split'] = 'test'
    with pytest.raises(ValueError, match='leaks across splits'):
        resolve_assets(manifest, tmp_path)
