"""Deterministic synthetic fixtures, not official competition artwork.

The fixed vectors contain no letters, labels, IDs or class-specific background.
Only public training template shapes are needed by the RGB reference detector.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
import yaml

GENERATOR_VERSION = 'procedural_v1'
OBJECT_LABELS = ('military_truck', 'mortar', 'tank', 'missile', 'ammo_box', 'drum')


def synthetic_image(label: str, size: int = 512) -> Image.Image:
    """Render a fixed monochrome silhouette with a common registration border."""
    image = Image.new('RGBA', (512, 512), (245, 245, 245, 255))
    d = ImageDraw.Draw(image)
    ink = (28, 28, 28, 255)
    d.rectangle((16, 16, 495, 495), outline=ink, width=12)
    if label == 'military_truck':
        d.rectangle((85, 200, 315, 335), fill=ink)
        d.polygon([(315, 245), (375, 245), (425, 300), (425, 355), (315, 355)], fill=ink)
        d.rectangle((330, 260, 365, 290), fill='white')
        for x in (135, 255, 380): d.ellipse((x-30, 325, x+30, 385), fill=ink)
    elif label == 'mortar':
        d.polygon([(150, 370), (310, 345), (365, 385), (120, 410)], fill=ink)
        d.line((235, 345, 345, 100), fill=ink, width=43)
        d.line((235, 260, 165, 370), fill=ink, width=18)
        d.line((235, 260, 300, 365), fill=ink, width=18)
    elif label == 'tank':
        d.rounded_rectangle((85, 285, 420, 385), radius=45, fill=ink)
        d.rectangle((120, 265, 385, 335), fill=ink)
        d.rectangle((190, 205, 305, 280), fill=ink)
        d.rectangle((275, 221, 440, 244), fill=ink)
        for x in (140, 205, 270, 335, 380): d.ellipse((x-13, 332, x+13, 358), fill='white')
    elif label == 'missile':
        d.polygon([(255, 70), (300, 155), (300, 355), (255, 400), (210, 355), (210, 155)], fill=ink)
        d.polygon([(210, 285), (130, 390), (210, 365)], fill=ink)
        d.polygon([(300, 285), (380, 390), (300, 365)], fill=ink)
        d.line((255, 415, 255, 450), fill=ink, width=18)
    elif label == 'ammo_box':
        d.polygon([(105, 190), (365, 190), (410, 235), (150, 235)], outline=ink, fill=(200, 200, 200), width=13)
        d.polygon([(105, 190), (150, 235), (150, 390), (105, 345)], outline=ink, fill=(220, 220, 220), width=13)
        d.rectangle((150, 235, 410, 390), outline=ink, width=16)
        d.rectangle((230, 280, 325, 315), outline=ink, width=10)
    elif label == 'drum':
        d.rectangle((150, 145, 360, 385), fill=(210, 210, 210), outline=ink, width=12)
        d.ellipse((150, 95, 360, 190), fill=(235, 235, 235), outline=ink, width=12)
        d.arc((150, 335, 360, 430), 0, 180, fill=ink, width=12)
        d.line((150, 385, 150, 145), fill=ink, width=12)
        d.line((360, 385, 360, 145), fill=ink, width=12)
        for y in (235, 310): d.line((153, y, 357, y), fill=ink, width=16)
    elif label == 'COMMS':
        d.line((255, 130, 255, 405), fill=ink, width=20)
        d.polygon([(255, 130), (165, 405), (345, 405)], outline=ink, width=12)
        d.arc((120, 70, 390, 290), 210, 330, fill=ink, width=13)
        d.arc((165, 105, 345, 250), 210, 330, fill=ink, width=13)
    elif label == 'OUTPOST':
        d.rectangle((140, 150, 370, 245), outline=ink, width=16)
        for x in (170, 340): d.line((x, 245, x, 420), fill=ink, width=18)
        d.line((175, 250, 335, 410), fill=ink, width=16)
        d.line((335, 250, 175, 410), fill=ink, width=16)
        d.polygon([(115, 150), (255, 70), (395, 150)], fill=ink)
    elif label == 'RADAR':
        d.pieslice((110, 80, 380, 330), 30, 210, fill=ink)
        d.line((250, 290, 250, 405), fill=ink, width=24)
        d.line((170, 410, 335, 410), fill=ink, width=24)
    else:
        for y in range(120, 390, 60):
            d.rectangle((90, y, 420, y+16), fill=ink)
            for x in range(90 + (30 if y % 120 else 0), 420, 90): d.rectangle((x, y, x+10, y+60), fill=ink)
    return image if size == 512 else image.resize((size, size), Image.Resampling.LANCZOS)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class ResolvedAssets:
    manifest: dict[str, Any]
    root: Path
    manifest_path: Path

    def path_for(self, asset_id: str) -> Path:
        asset = next((a for a in self.manifest['assets'] if a['asset_id'] == asset_id), None)
        if asset is None: raise ValueError(f'asset_id {asset_id!r} is absent from resolved manifest')
        relative = Path(asset['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError(f'asset {asset_id}: resolved path must remain relative to manifest')
        path = self.root / relative
        if not path.is_file() or file_sha256(path) != asset['sha256']:
            raise ValueError(f'asset {asset_id}: file missing or SHA256 mismatch')
        return path


def resolve_assets(manifest: dict[str, Any] | str | Path, out: str | Path, base_dir: str | Path | None = None) -> ResolvedAssets:
    """Resolve into *out*, retaining source manifest and import digest checks."""
    if isinstance(manifest, (str, Path)):
        source_path = Path(manifest)
        base_dir = source_path.parent
        source = yaml.safe_load(source_path.read_text())
    else:
        source = copy.deepcopy(manifest)
    base = Path(base_dir or '.')
    output = Path(out)
    output.mkdir(parents=True, exist_ok=True)
    resolved = copy.deepcopy(source)
    seen: set[str] = set()
    groups: dict[str, str] = {}
    for asset in resolved['assets']:
        identifier = asset['asset_id']
        if identifier in seen: raise ValueError(f'duplicate asset_id {identifier}')
        seen.add(identifier)
        if '/' in identifier or '\\' in identifier or identifier in ('.', '..'):
            raise ValueError(f'asset_id is not a safe filename: {identifier!r}')
        if asset['split_group'] in groups and groups[asset['split_group']] != asset['split']:
            raise ValueError(f"split_group {asset['split_group']} leaks across splits")
        groups[asset['split_group']] = asset['split']
        destination = output / (identifier + '.png')
        if asset['generator'] == GENERATOR_VERSION:
            synthetic_image(asset['label']).save(destination, format='PNG', optimize=False)
        elif asset['generator'] == 'import':
            path = base / str(asset['path'])
            if not path.is_file() or not asset.get('sha256') or file_sha256(path) != asset['sha256']:
                raise ValueError(f'asset {identifier}: imported file missing or SHA256 mismatch')
            # Copy original bytes so manifest preserves authoritative digest.
            destination = output / (identifier + path.suffix)
            destination.write_bytes(path.read_bytes())
        else: raise ValueError(f"asset {identifier}: unsupported generator {asset['generator']}")
        asset['path'] = destination.name
        asset['sha256'] = file_sha256(destination)
    path = output / 'resolved_manifest.yaml'
    path.write_text(yaml.safe_dump(resolved, sort_keys=False, allow_unicode=True))
    metadata = {'generator_version': GENERATOR_VERSION, 'source_manifest_sha256': manifest_sha256(source)}
    (output / 'resolution.json').write_text(json.dumps(metadata, indent=2) + '\n')
    return ResolvedAssets(resolved, output, path)


def load_resolved_assets(path: str | Path, source_manifest: dict[str, Any] | None = None) -> ResolvedAssets:
    manifest_path = Path(path)
    resolved = ResolvedAssets(yaml.safe_load(manifest_path.read_text()), manifest_path.parent, manifest_path)
    metadata = json.loads((resolved.root / 'resolution.json').read_text())
    if metadata['generator_version'] != GENERATOR_VERSION: raise ValueError('resolved generator version mismatch')
    if source_manifest is not None:
        if resolved.manifest['manifest_id'] != source_manifest['manifest_id']:
            raise ValueError('resolved manifest_id mismatch')
        if metadata['source_manifest_sha256'] != manifest_sha256(source_manifest):
            raise ValueError('resolved source manifest hash mismatch')
    for asset in resolved.manifest['assets']: resolved.path_for(asset['asset_id'])
    return resolved
