import * as THREE from 'three';
import { describe, expect, it } from 'vitest';
import { wallPoint, wallShape, type WallDef } from './walls';

/** Characterization of the wall outline: what the slab builder does today. */
function wall(openings: WallDef['openings'], ext?: [number, number]): WallDef {
  return {
    name: 'north', origin: new THREE.Vector3(-2, 0, -1), u: new THREE.Vector3(1, 0, 0), n: new THREE.Vector3(0, 0, 1),
    length: 4, thickness: 0.1, openings, panels: [], height: 2.5, ext,
  };
}

const outline = (shape: THREE.Shape) => shape.getPoints().map(p => [+p.x.toFixed(3), +p.y.toFixed(3)]);

describe('wall outline', () => {
  it('runs past both ends by 0.3 m and up to the wall height', () => {
    expect(outline(wallShape(wall([])))).toEqual([[-0.3, 0], [4.3, 0], [4.3, 2.5], [-0.3, 2.5], [-0.3, 0]]);
  });

  it('honours per-end extensions, such as zero at an outside corner', () => {
    expect(outline(wallShape(wall([], [0, 0.1])))).toEqual([[0, 0], [4.1, 0], [4.1, 2.5], [0, 2.5], [0, 0]]);
  });

  it('cuts an opening that reaches the floor as a notch in the outline, not a hole', () => {
    const shape = wallShape(wall([{ kind: 'rect', u0: 1, u1: 2, v0: 0, v1: 2 }]));

    expect(shape.holes).toHaveLength(0);
    expect(outline(shape).slice(0, 6)).toEqual([[-0.3, 0], [1, 0], [1, 2], [2, 2], [2, 0], [4.3, 0]]);
  });

  it('cuts a window above the floor as a hole', () => {
    const shape = wallShape(wall([{ kind: 'rect', u0: 1, u1: 2, v0: 1, v1: 2 }]));

    expect(shape.holes).toHaveLength(1);
    expect(shape.holes[0].getPoints().map(p => [p.x, p.y])).toEqual([[1, 1], [1, 2], [2, 2], [2, 1], [1, 1]]);
  });

  it('orders several floor openings from left to right along the wall', () => {
    const shape = wallShape(wall([{ kind: 'rect', u0: 3, u1: 3.5, v0: 0, v1: 2 }, { kind: 'rect', u0: 0.5, u1: 1, v0: 0, v1: 2 }]));

    expect(outline(shape).slice(1, 9).map(([u]) => u)).toEqual([0.5, 0.5, 1, 1, 3, 3, 3.5, 3.5]);
  });
});

describe('wall coordinates', () => {
  it('maps (u, v, out) to world space along the wall, up and into the room', () => {
    expect(wallPoint(wall([]), 1, 2, 0.5).toArray()).toEqual([-1, 2, -0.5]);
  });
});
