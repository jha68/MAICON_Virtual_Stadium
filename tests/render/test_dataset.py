"""Evaluator private export: actual geometry masks and hashes, never RGB labels."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pytest
from PIL import Image

from maicon_sim.config.loader import load_scenario
from maicon_sim.evaluation.dataset import export_dataset

pytestmark=pytest.mark.render


def test_ISO_002_dataset_private_files_hashes_and_hidden_inventory(tmp_path):
    config=load_scenario('examples/scenario_perception_gallery.yaml')
    original=json.dumps(config.scenario,sort_keys=True)
    manifest=export_dataset(config,tmp_path,slots=['B-1'])
    assert not (tmp_path/'public').exists()
    assert json.dumps(config.scenario,sort_keys=True)==original
    assert manifest['mode']=='evaluator_only_initial_scene' and not manifest['simulated_advance']
    assert manifest['captured_tick']==0 and manifest['seed']==config.scenario['seed']
    assert manifest['renderer']['api_version']>0
    for name,expected in manifest['files'].items():
        assert name.startswith('private/')
        assert hashlib.sha256((tmp_path/name).read_bytes()).hexdigest()==expected
    inventory=json.loads((tmp_path/manifest['truth_inventory_file']).read_text())
    assert len(inventory['faces'])==14
    assert inventory['objects_by_sector']['B-S1']=={'TANK':1}
    frame=manifest['frames'][0];annotations=json.loads((tmp_path/frame['annotations_file']).read_text())
    by_face={value['face_id']:value for value in annotations['all_faces']}
    visible=by_face['box_B1/east'];hidden=by_face['box_B1/west']
    assert visible['class']=='TANK' and visible['visible_pixels']>100
    assert visible['visible_bbox_xyxy_px'] is not None
    assert .8<visible['visible_fraction']<=1.
    assert hidden['visible_pixels']==0 and hidden['visible_bbox_xyxy_px'] is None
    assert hidden['visible_fraction']==0
    assert any(value['face_id']=='box_B1/west' for value in inventory['faces'])
    assert not any(value['face_id']=='box_B1/west' for value in annotations['visible_annotations'])
    depth=np.load(tmp_path/frame['depth_file'],allow_pickle=False)
    invalid=np.load(tmp_path/frame['invalid_mask_file'],allow_pickle=False)
    segmentation=np.load(tmp_path/frame['segmentation_file'],allow_pickle=False)
    assert depth.shape==invalid.shape==segmentation.shape==(480,640)
    assert invalid.dtype==np.bool_ and segmentation.dtype==np.int32
    mask=np.asarray(Image.open((tmp_path/frame['annotations_file']).parent/visible['mask_file']))
    assert np.count_nonzero(mask)==visible['visible_pixels']
    assert mask.shape==(480,640)


def test_dataset_refuses_unknown_slot_before_render(tmp_path):
    config=load_scenario('examples/scenario_perception_gallery.yaml')
    with pytest.raises(ValueError,match='known robot slots'):
        export_dataset(config,tmp_path,slots=['R-S1'])
    assert not (tmp_path/'private/dataset_manifest.json').exists()


def test_dataset_opaque_occlusion_preserves_full_truth(tmp_path):
    config=load_scenario('examples/scenario_perception_gallery.yaml')
    config.scenario['boxes'].append({'box_id':'dataset_occluder','sector_id':'B-S1',
        'pose':{'x_m':2.16,'y_m':4.2,'yaw_rad':0.},'size_m':[.1,.5,.6],
        'faces':[{'side':'east','asset_id':'decoy_wall','kind':'decoy'}]})
    manifest=export_dataset(config,tmp_path,slots=['B-1'])
    frame=manifest['frames'][0]
    data=json.loads((tmp_path/frame['annotations_file']).read_text())
    target=next(value for value in data['all_faces'] if value['face_id']=='box_B1/east')
    assert target['full_projection_area_px']>100
    assert target['visible_pixels']==0 and target['visible_fraction']==0
    inventory=json.loads((tmp_path/manifest['truth_inventory_file']).read_text())
    assert inventory['objects_by_sector']['B-S1']=={'TANK':1}
    assert any(value['face_id']=='box_B1/east' for value in inventory['faces'])
