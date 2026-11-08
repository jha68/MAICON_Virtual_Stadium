import numpy as np
import pytest
from maicon_sim.backends.bullet.asset_builder import OBJECT_LABELS, synthetic_image
from maicon_sim.perception.synthetic_template import SyntheticTemplateDetector

pytestmark = pytest.mark.render


@pytest.mark.parametrize('label', OBJECT_LABELS)
def test_public_template_gallery(label):
    image = synthetic_image(label).convert('RGB').resize((240,240))
    bgr = np.full((480,640,3), 180, np.uint8)
    bgr[120:360,200:440] = np.asarray(image)[...,::-1]
    detections = SyntheticTemplateDetector().detect(bgr)
    assert len(detections) == 1, detections
    d = detections[0]
    assert max(d['class_probs'],key=d['class_probs'].get) == label
    assert abs(sum(d['class_probs'].values())-1) < 1e-6
    assert set(d) == {'kind','bbox_xyxy_px','class_probs','confidence'}


def test_blank_has_no_detections():
    assert SyntheticTemplateDetector().detect(np.full((480,640,3),245,np.uint8)) == []


def test_rotations_and_unlabeled_pixels_only():
    detector = SyntheticTemplateDetector()
    for k in range(4):
        image = np.asarray(synthetic_image('tank').convert('RGB').resize((240,240)))
        bgr = np.full((480,640,3),180,np.uint8)
        bgr[120:360,200:440] = np.rot90(image,k)[...,::-1]
        detections = detector.detect(bgr)
        assert len(detections)==1
        assert max(detections[0]['class_probs'],key=detections[0]['class_probs'].get)=='tank'


@pytest.mark.parametrize('label', ['COMMS','OUTPOST','RADAR','wall'])
def test_non_scoring_fixture_not_object(label):
    bgr = np.full((480,640,3), 180, np.uint8)
    bgr[120:360,200:440] = np.asarray(synthetic_image(label).convert('RGB').resize((240,240)))[...,::-1]
    assert SyntheticTemplateDetector().detect(bgr) == []
