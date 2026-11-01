import * as THREE from 'three';
import { describe, expect, it } from 'vitest';
import { stabilizeWallOverlaps } from './wall-overlaps';
import type { BuiltRoom } from './types';
import type { WallDef } from './walls';

/** Characterization of the coincident slab face audit: what it reports and rewrites today. */
type Wall = BuiltRoom['walls'][number];

const def = (name: string, n = new THREE.Vector3(0, 0, 1)): WallDef => ({
  name, origin: new THREE.Vector3(), u: new THREE.Vector3(1, 0, 0), n, length: 1, thickness: 0.1, openings: [], panels: [],
});

/**
 * A wall whose slab is a 1 m square facing +z, centered at `at`. PlaneGeometry splits it into
 * an upper-left triangle (y >= x) and a lower-right one (y < x).
 */
type Point = [number, number, number];
interface SlabOptions {
  n?: THREE.Vector3;
  meshName?: string;
  /** rotates the slab through its world transform */
  turn?: THREE.Euler;
  /** remaps the square's vertices exactly, without trigonometric round-off */
  face?: (p: Point) => Point;
  size?: number;
  room?: string;
}
function wall(name: string, at: Point, options: SlabOptions = {}): Wall {
  const geometry = new THREE.PlaneGeometry(options.size ?? 1, options.size ?? 1);
  const { face } = options;
  if (face) {
    const pos = geometry.getAttribute('position');
    for (let i = 0; i < pos.count; i++) pos.setXYZ(i, ...face([pos.getX(i), pos.getY(i), pos.getZ(i)]));
  }
  const slab = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
  slab.name = options.meshName ?? 'slab';
  slab.position.set(...at);
  if (options.turn) slab.rotation.copy(options.turn);
  if (options.room) slab.userData.houseRoom = options.room;
  const group = new THREE.Group();
  group.add(slab);
  return { def: def(name, options.n), group };
}
const slabOf = (w: Wall) => w.group.children[0] as THREE.Mesh;
const materialsOf = (w: Wall) => slabOf(w).material as THREE.Material[];
const rounded = (overlaps: { first: string; second: string; area: number }[]) =>
  overlaps.map(o => ({ ...o, area: Math.round(o.area * 1e6) / 1e6 }));

describe('wall overlap audit', () => {
  it('reports nothing when no slab faces coincide', () => {
    expect(stabilizeWallOverlaps([wall('a', [0, 0, 0]), wall('b', [2, 0, 0])])).toEqual([]);
  });

  it('reports the area two coplanar slabs share, named by room and wall', () => {
    expect(rounded(stabilizeWallOverlaps([wall('a', [0, 0, 0]), wall('b', [0.5, 0, 0])]))).toEqual([{ first: 'room/a', second: 'room/b', area: 0.5 }]);
  });

  it('names a slab after the house room it belongs to', () => {
    const [overlap] = stabilizeWallOverlaps([wall('a', [0, 0, 0], { room: 'kitchen' }), wall('b', [0.5, 0, 0], { room: 'hall' })]);

    expect([overlap.first, overlap.second]).toEqual(['kitchen/a', 'hall/b']);
  });

  it('measures the shared area of a corner overlap clipped through both triangles', () => {
    // a 0.4 x 0.3 rectangle straddling the diagonal of both squares
    expect(rounded(stabilizeWallOverlaps([wall('a', [0, 0, 0]), wall('b', [0.6, 0.7, 0])]))[0].area).toBe(0.12);
  });

  it('ignores slabs that only touch along an edge', () => {
    expect(stabilizeWallOverlaps([wall('a', [0, 0, 0]), wall('b', [1, 0, 0])])).toEqual([]);
  });

  it('ignores coplanar faces that face opposite ways', () => {
    const back = wall('b', [0.5, 0, 0], { turn: new THREE.Euler(0, Math.PI, 0) });

    expect(stabilizeWallOverlaps([wall('a', [0, 0, 0]), back])).toEqual([]);
  });

  it('ignores parallel faces more than 0.01 mm apart', () => {
    expect(stabilizeWallOverlaps([wall('a', [0, 0, 0]), wall('b', [0.5, 0, 2e-5])])).toEqual([]);
  });

  it('treats faces within 0.01 mm of each other as coincident', () => {
    expect(stabilizeWallOverlaps([wall('a', [0, 0, 0]), wall('b', [0.5, 0, 5e-6])])).toHaveLength(1);
  });

  it('only audits meshes named slab', () => {
    expect(stabilizeWallOverlaps([wall('a', [0, 0, 0]), wall('b', [0.5, 0, 0], { meshName: 'baseboard' })])).toEqual([]);
  });

  it('never compares a slab with itself', () => {
    const w = wall('a', [0, 0, 0]);
    const doubled = new THREE.Mesh(new THREE.PlaneGeometry(1, 1).toNonIndexed(), new THREE.MeshBasicMaterial());
    const geo = doubled.geometry;
    const both = new Float32Array([...geo.getAttribute('position').array, ...geo.getAttribute('position').array]);
    geo.setAttribute('position', new THREE.BufferAttribute(both, 3));
    doubled.name = 'slab';
    w.group.clear();
    w.group.add(doubled);

    expect(stabilizeWallOverlaps([w])).toEqual([]);
  });

  it('skips degenerate triangles', () => {
    const w = wall('a', [0, 0, 0]);
    const flat = new THREE.BufferGeometry();
    flat.setAttribute('position', new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0, 2, 0, 0], 3));
    const mesh = new THREE.Mesh(flat, new THREE.MeshBasicMaterial());
    mesh.name = 'slab';
    const other: Wall = { def: def('b'), group: new THREE.Group().add(mesh) };

    expect(stabilizeWallOverlaps([w, other])).toEqual([]);
  });

  it.each([
    ['x', ([x, y, z]: Point): Point => [z, y, -x], [0, 0, 0.5]],
    ['y', ([x, y, z]: Point): Point => [x, z, -y], [0.5, 0, 0]],
    ['-z', ([x, y, z]: Point): Point => [-x, y, -z], [0.5, 0, 0]],
  ] as [string, (p: Point) => Point, Point][])('measures the shared area of slabs facing %s', (_, face, shift) => {
    const overlaps = stabilizeWallOverlaps([wall('a', [0, 0, 0], { face }), wall('b', shift, { face })]);

    expect(rounded(overlaps)[0].area).toBe(0.5);
  });

  it('measures the true shared area of slabs facing a tilted normal', () => {
    const turn = new THREE.Euler(0, Math.PI / 4, 0);
    const overlaps = stabilizeWallOverlaps([wall('a', [0, 0, 0], { turn }), wall('b', [Math.SQRT1_2 / 2, 0, -Math.SQRT1_2 / 2], { turn })]);

    expect(rounded(overlaps)[0].area).toBe(0.5);
  });

  it('measures the shared area of slabs of any size', () => {
    const overlaps = stabilizeWallOverlaps([wall('a', [0, 0, 0], { size: 2 }), wall('b', [1, 0, 0], { size: 2 })]);

    expect(rounded(overlaps)[0].area).toBe(2);
  });

  it('finds coincident faces on a plane away from the origin', () => {
    expect(rounded(stabilizeWallOverlaps([wall('a', [0, 0, 3]), wall('b', [0.5, 0, 3])]))[0].area).toBe(0.5);
  });

  it('places each slab through the transforms of the wall group it hangs from', () => {
    const b = wall('b', [0, 0, 0]);
    b.group.position.x = 0.5;

    expect(rounded(stabilizeWallOverlaps([wall('a', [0, 0, 0]), b]))[0].area).toBe(0.5);
  });

  it('ignores a face tilted off the plane even when one of its edges lies in it', () => {
    // 0.001 rad about the slab's left edge: normals still within 1e-6 of parallel, far corner 1 mm off
    const tilted = wall('b', [0, 0, 0], { face: ([x, y, z]: Point): Point => [x, y, z + (x + 0.5) * 0.001] });

    expect(stabilizeWallOverlaps([wall('a', [0, 0, 0]), tilted])).toEqual([]);
  });

  it('lists the overlaps from the largest to the smallest', () => {
    const overlaps = stabilizeWallOverlaps([wall('a', [0, 0, 0]), wall('b', [0.9, 0, 0]), wall('c', [0, 5, 0]), wall('d', [0.2, 5, 0])]);

    expect(overlaps.map(o => [o.first, o.second])).toEqual([['room/c', 'room/d'], ['room/a', 'room/b']]);
  });

  it('adds up the area of every triangle pair between the same two slabs', () => {
    const overlaps = stabilizeWallOverlaps([wall('a', [0, 0, 0]), wall('b', [0, 0, 0])]);

    expect(rounded(overlaps)).toEqual([{ first: 'room/a', second: 'room/b', area: 1 }]);
  });
});

describe('wall overlap depth bias', () => {
  it('leaves slabs without coincident faces untouched', () => {
    const a = wall('a', [0, 0, 0]);
    const { geometry, material } = slabOf(a);
    stabilizeWallOverlaps([a, wall('b', [2, 0, 0])]);

    expect([slabOf(a).geometry, slabOf(a).material]).toEqual([geometry, material]);
  });

  it('moves only the coincident triangles to a biased copy of their material', () => {
    // b overlaps a's lower-right triangle only, and only with b's upper-left one
    const a = wall('a', [0, 0, 0]), b = wall('b', [0.9, -0.9, 0]);
    stabilizeWallOverlaps([a, b]);

    expect(slabOf(a).geometry.groups).toEqual([{ start: 0, count: 3, materialIndex: 0 }, { start: 3, count: 3, materialIndex: 1 }]);
    expect(slabOf(b).geometry.groups).toEqual([{ start: 0, count: 3, materialIndex: 1 }, { start: 3, count: 3, materialIndex: 0 }]);
  });

  it('merges neighbouring triangles that share a material into one group', () => {
    const a = wall('a', [0, 0, 0]);
    stabilizeWallOverlaps([a, wall('b', [0.5, 0, 0])]);

    expect(slabOf(a).geometry.groups).toEqual([{ start: 0, count: 6, materialIndex: 1 }]);
  });

  it('shares one biased copy among the triangles of a slab with the same material and priority', () => {
    const a = wall('a', [0, 0, 0]);
    stabilizeWallOverlaps([a, wall('b', [0.5, 0, 0])]);

    expect(materialsOf(a)).toHaveLength(2);
  });

  it('pulls later slabs further forward, and interior faces ahead of every end cap', () => {
    // front: the face points along its wall normal (interior paint); back: an end cap
    const backward = new THREE.Vector3(0, 0, -1);
    const walls = [wall('a', [0, 0, 0], { n: backward }), wall('b', [0.5, 0, 0], { n: backward }), wall('c', [0.25, 0, 0])];
    stabilizeWallOverlaps(walls);

    expect(walls.map(w => materialsOf(w)[1].polygonOffsetUnits)).toEqual([-1, -2, -6]);
  });

  it('turns polygon offset on with a zero slope factor in the biased copy', () => {
    const a = wall('a', [0, 0, 0]);
    stabilizeWallOverlaps([a, wall('b', [0.5, 0, 0])]);
    const biased = materialsOf(a)[1];

    expect([biased.polygonOffset, biased.polygonOffsetFactor]).toEqual([true, 0]);
  });

  it('keeps the original material first and never mutates it', () => {
    const a = wall('a', [0, 0, 0]);
    const original = slabOf(a).material as THREE.Material;
    stabilizeWallOverlaps([a, wall('b', [0.5, 0, 0])]);

    expect(materialsOf(a)[0]).toBe(original);
    expect([original.polygonOffset, original.polygonOffsetUnits]).toEqual([false, 0]);
  });

  it('rewrites a copy of the slab geometry, leaving the shared original intact', () => {
    const a = wall('a', [0, 0, 0]);
    const original = slabOf(a).geometry;
    stabilizeWallOverlaps([a, wall('b', [0.5, 0, 0])]);

    expect(slabOf(a).geometry).not.toBe(original);
    expect(original.groups).toEqual([]);
  });

  it('biases each material of a multi-material slab separately', () => {
    const a = wall('a', [0, 0, 0]);
    const paint = new THREE.MeshBasicMaterial({ color: 'red' }), trim = new THREE.MeshBasicMaterial({ color: 'blue' });
    const slab = slabOf(a);
    slab.material = [paint, trim];
    slab.geometry.addGroup(0, 3, 0);
    slab.geometry.addGroup(3, 3, 1);
    stabilizeWallOverlaps([a, wall('b', [0, 0, 0])]);

    expect(slab.geometry.groups.map(g => g.materialIndex)).toEqual([2, 3]);
    expect(materialsOf(a).map(m => m.polygonOffsetUnits)).toEqual([0, 0, -3, -3]);
    expect(materialsOf(a).map(m => (m as THREE.MeshBasicMaterial).color.getHexString())).toEqual(['ff0000', '0000ff', 'ff0000', '0000ff']);
  });

  it('audits slabs without an index buffer', () => {
    const a = wall('a', [0, 0, 0]);
    slabOf(a).geometry = slabOf(a).geometry.toNonIndexed();
    stabilizeWallOverlaps([a, wall('b', [0.5, 0, 0])]);

    expect(slabOf(a).geometry.groups).toEqual([{ start: 0, count: 6, materialIndex: 1 }]);
  });
});
