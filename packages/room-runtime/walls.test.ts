import * as THREE from 'three';
import { describe, expect, it, vi } from 'vitest';

// The real palette needs preloaded textures and a DOM canvas; the walls only need distinct materials.
vi.mock('./materials', () => {
  const named = (name: string) => Object.assign(new THREE.MeshBasicMaterial(), { name });
  const palette = { wall: named('wall'), trim: named('trim'), glass: named('glass') };
  return { materials: () => palette };
});

import { materials } from './materials';
import { buildWall, wallMatrix, wallPoint, wallShape, type WallDef } from './walls';

/** Characterization of the wall builder: what it produces today. */
function wall(openings: WallDef['openings'], ext?: [number, number]): WallDef {
  return {
    name: 'north', origin: new THREE.Vector3(-2, 0, -1), u: new THREE.Vector3(1, 0, 0), n: new THREE.Vector3(0, 0, 1),
    length: 4, thickness: 0.1, openings, panels: [], height: 2.5, ext,
  };
}

const outline = (shape: THREE.Path) => shape.getPoints().map(p => [+p.x.toFixed(3), +p.y.toFixed(3)]);
const mm = (n: number) => Math.round(n * 1000) / 1000 + 0; // + 0 turns -0 into 0
/** World-space bounding box as [minX, minY, minZ, maxX, maxY, maxZ], rounded to the millimetre. */
const extent = (o: THREE.Object3D) => {
  const box = new THREE.Box3().setFromObject(o);
  return [...box.min.toArray(), ...box.max.toArray()].map(mm);
};
const named = (group: THREE.Object3D, name: string) => group.children.filter(c => c.name === name);
const slabOf = (group: THREE.Object3D) => group.getObjectByName('slab') as THREE.Mesh;
const triangleCount = (o: THREE.Object3D) => ((o as THREE.Mesh).geometry.index?.count ?? 0) / 3;

/** Slab triangles of one material group, in the slab's local (u, v, depth) space. */
function triangles(slab: THREE.Mesh, materialIndex: number) {
  const geo = slab.geometry;
  const pos = geo.getAttribute('position');
  const index = geo.index;
  if (!index) throw new Error('the slab geometry is indexed');
  const group = geo.groups.find(g => g.materialIndex === materialIndex);
  if (!group) return [];
  const out: THREE.Vector3[][] = [];
  for (let i = group.start; i < group.start + group.count; i += 3) {
    out.push([0, 1, 2].map(k => new THREE.Vector3().fromBufferAttribute(pos, index.getX(i + k))));
  }
  return out;
}
const PAINT = 0, TRIM = 1;
/** Triangles lying entirely in the plane u = x (an end cap or a vertical jamb). */
const atU = (tris: THREE.Vector3[][], x: number) => tris.filter(t => t.every(p => Math.abs(p.x - x) < 1e-6));

describe('wall outline', () => {
  it('runs past both ends by 0.3 m and up to the wall height', () => {
    expect(outline(wallShape(wall([])))).toEqual([[-0.3, 0], [4.3, 0], [4.3, 2.5], [-0.3, 2.5], [-0.3, 0]]);
  });

  it('honours per-end extensions, such as zero at an outside corner', () => {
    expect(outline(wallShape(wall([], [0, 0.1])))).toEqual([[0, 0], [4.1, 0], [4.1, 2.5], [0, 2.5], [0, 0]]);
  });

  it('rises to the legacy 3.24 m when the wall has no height of its own', () => {
    const w = { ...wall([]), height: undefined };

    expect(outline(wallShape(w))[2]).toEqual([4.3, 3.24]);
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

  it('cuts an arched opening as a hole topped by a half circle over the springline', () => {
    const hole = wallShape(wall([{ kind: 'arch', u0: 1, u1: 2, v0: 0.8, spring: 2.2 }])).holes[0];
    const points = outline(hole);

    expect(points.slice(0, 2)).toEqual([[1, 0.8], [1, 2.2]]);
    expect(points).toContainEqual([1.5, 2.7]);
    expect(Math.max(...points.map(([, v]) => v))).toBe(2.7);
    expect(points.slice(-2)).toEqual([[2, 0.8], [1, 0.8]]);
  });

  it('cuts an arched opening as a hole even when it starts at the floor', () => {
    const shape = wallShape(wall([{ kind: 'arch', u0: 1, u1: 2, v0: 0, spring: 2 }]));

    expect(shape.holes).toHaveLength(1);
    expect(outline(shape)).toHaveLength(5);
  });
});

describe('wall coordinates', () => {
  it('maps (u, v, out) to world space along the wall, up and into the room', () => {
    expect(wallPoint(wall([]), 1, 2, 0.5).toArray()).toEqual([-1, 2, -0.5]);
  });

  it('maps wall-local (u, v, out) through the wall matrix to the same world point as wallPoint', () => {
    const w: WallDef = { ...wall([]), origin: new THREE.Vector3(3, 0, 1), u: new THREE.Vector3(0, 0, -1), n: new THREE.Vector3(1, 0, 0) };

    expect(new THREE.Vector3(1, 2, 0.5).applyMatrix4(wallMatrix(w)).toArray()).toEqual([3.5, 2, 0]);
  });
});

describe('wall slab', () => {
  it('names the wall group after the wall', () => {
    expect(buildWall(wall([])).name).toBe('wall-north');
  });

  it('extrudes the outline behind the interior face, through the wall thickness', () => {
    expect(extent(slabOf(buildWall(wall([]))))).toEqual([-2.3, 0, -1.1, 2.3, 2.5, -1]);
  });

  it('runs the slab past the ends by the extension given to the builder', () => {
    expect(extent(slabOf(buildWall(wall([]), materials(), 0.5)))).toEqual([-2.5, 0, -1.1, 2.5, 2.5, -1]);
  });

  it('paints the slab with the palette wall colour and its side faces with the palette trim', () => {
    const { wall: paint, trim } = materials();

    expect(slabOf(buildWall(wall([]))).material).toEqual([paint, trim]);
  });

  it('uses the wall own paint and trim materials when it supplies them', () => {
    const paint = new THREE.MeshBasicMaterial(), trim = new THREE.MeshBasicMaterial();
    const group = buildWall({ ...wall([]), material: paint, trimMaterial: trim });

    expect(slabOf(group).material).toEqual([paint, trim]);
    expect((named(group, 'baseboard')[0] as THREE.Mesh).material).toBe(trim);
  });

  it('splits the slab into one paint group followed by one trim group covering every triangle', () => {
    const geo = slabOf(buildWall(wall([]))).geometry;

    expect(geo.groups).toEqual([{ start: 0, count: 24, materialIndex: PAINT }, { start: 24, count: 12, materialIndex: TRIM }]);
    expect(geo.index?.count).toBe(36);
  });

  it('paints the end caps, which show at outside corners', () => {
    const slab = slabOf(buildWall(wall([])));

    expect(atU(triangles(slab, PAINT), -0.3)).toHaveLength(2);
    expect(atU(triangles(slab, PAINT), 4.3)).toHaveLength(2);
    expect(atU(triangles(slab, TRIM), -0.3)).toHaveLength(0);
    expect(atU(triangles(slab, TRIM), 4.3)).toHaveLength(0);
  });

  it('finds the end caps at each per-wall extension', () => {
    const slab = slabOf(buildWall(wall([], [0.2, 0.1])));

    expect(atU(triangles(slab, PAINT), -0.2)).toHaveLength(2);
    expect(atU(triangles(slab, PAINT), 4.1)).toHaveLength(2);
  });

  it('leaves the top and bottom edges of a plain slab in trim', () => {
    const trim = triangles(slabOf(buildWall(wall([]))), TRIM);

    expect(trim).toHaveLength(4);
    expect(trim.every(t => t.every(p => p.y === 0) || t.every(p => p.y === 2.5))).toBe(true);
  });

  it('leaves the window jambs in trim', () => {
    const slab = slabOf(buildWall(wall([{ kind: 'rect', u0: 1, u1: 2, v0: 1, v1: 2 }])));

    expect(atU(triangles(slab, TRIM), 1)).toHaveLength(2);
    expect(atU(triangles(slab, TRIM), 2)).toHaveLength(2);
    expect(atU(triangles(slab, PAINT), 1)).toHaveLength(0);
  });
});

describe('wall trim', () => {
  it('frames each picture panel with a molding standing 16 mm off the wall', () => {
    const group = buildWall({ ...wall([]), panels: [[0.5, 0.3, 1.5, 0.9], [2, 0.3, 3, 0.9]] });
    const panels = named(group, 'panel');

    expect(panels.map(extent)).toEqual([[-1.5, 0.3, -1, -0.5, 0.9, -0.984], [0, 0.3, -1, 1, 0.9, -0.984]]);
    expect((panels[0] as THREE.Mesh).material).toBe(materials().trim);
  });

  it('closes each panel frame into a loop of four mitered sides, without end caps', () => {
    const [panel] = named(buildWall({ ...wall([]), panels: [[0.5, 0.3, 1.5, 0.9]] }), 'panel');

    // 4 sides x 9 profile faces x 2 triangles
    expect(triangleCount(panel)).toBe(72);
  });

  it('runs a crown molding along the whole top, hanging 11 cm into the room', () => {
    const crowns = named(buildWall(wall([])), 'crown');

    expect(crowns.map(extent)).toEqual([[-2, 2.39, -1, 2, 2.5, -0.89]]);
  });

  it('leaves the crown ends open, as they run into the neighbouring walls', () => {
    const [crown] = named(buildWall(wall([])), 'crown');

    // 1 run x 15 profile faces x 2 triangles, no caps
    expect(triangleCount(crown)).toBe(30);
  });

  it('hangs the crown from the legacy 3.24 m top when the wall has no height of its own', () => {
    const [crown] = named(buildWall({ ...wall([]), height: undefined }), 'crown');

    expect(extent(crown)[4]).toBe(3.24);
  });

  it('leaves the crown out when the wall opts out of it', () => {
    expect(named(buildWall({ ...wall([]), crown: false }), 'crown')).toHaveLength(0);
  });

  it('runs one baseboard along a wall without gaps', () => {
    expect(named(buildWall(wall([])), 'baseboard').map(extent)).toEqual([[-2, 0, -1, 2, 0.162, -0.982]]);
  });

  it('interrupts the baseboard at each gap, whatever order the gaps are listed in', () => {
    const group = buildWall({ ...wall([]), baseboardGaps: [[3, 3.5], [1, 2]] });

    expect(named(group, 'baseboard').map(b => extent(b)[0])).toEqual([-2, 0, 1.5]);
    expect(named(group, 'baseboard').map(b => extent(b)[3])).toEqual([-1, 1, 2]);
  });

  it('skips a baseboard run of 1 cm or less', () => {
    const group = buildWall({ ...wall([]), baseboardGaps: [[0.01, 1], [3.99, 4]] });

    expect(named(group, 'baseboard').map(extent)).toEqual([[-1, 0, -1, 1.99, 0.162, -0.982]]);
  });

  it('keeps a baseboard run just over 1 cm', () => {
    const group = buildWall({ ...wall([]), baseboardGaps: [[0.02, 1]] });

    expect(named(group, 'baseboard')).toHaveLength(2);
  });

  it('stops the baseboard at the outer edge of a door casing', () => {
    const group = buildWall(wall([{ kind: 'rect', u0: 1, u1: 2, v0: 0, v1: 2, casing: true }]));

    expect(named(group, 'baseboard').map(b => [extent(b)[0], extent(b)[3]])).toEqual([[-2, -1.095], [0.095, 2]]);
  });

  it('runs the baseboard through a floor opening without casing', () => {
    expect(named(buildWall(wall([{ kind: 'rect', u0: 1, u1: 2, v0: 0, v1: 2 }])), 'baseboard')).toHaveLength(1);
  });

  it('runs the baseboard under a cased window', () => {
    expect(named(buildWall(wall([{ kind: 'rect', u0: 1, u1: 2, v0: 1, v1: 2, casing: true }])), 'baseboard')).toHaveLength(1);
  });

  it('cases a door up both jambs and across the head, down to the floor', () => {
    const casings = named(buildWall(wall([{ kind: 'rect', u0: 1, u1: 2, v0: 0, v1: 2, casing: true }])), 'casing');

    expect(casings.map(extent)).toEqual([[-1.095, 0, -1, 0.095, 2.095, -0.972]]);
  });

  it('cases a window all the way around, sill included', () => {
    const casings = named(buildWall(wall([{ kind: 'rect', u0: 1, u1: 2, v0: 1, v1: 2, casing: true }])), 'casing');

    expect(casings.map(extent)).toEqual([[-1.095, 0.905, -1, 0.095, 2.095, -0.972]]);
  });

  it('adds no casing to an opening that does not ask for one', () => {
    const group = buildWall(wall([{ kind: 'rect', u0: 1, u1: 2, v0: 0, v1: 2 }, { kind: 'rect', u0: 2.5, u1: 3, v0: 1, v1: 2 }]));

    expect(named(group, 'casing')).toHaveLength(0);
  });

  it('adds no window to a rectangular opening', () => {
    expect(named(buildWall(wall([{ kind: 'rect', u0: 1, u1: 2, v0: 1, v1: 2, casing: true }])), 'window')).toHaveLength(0);
  });
});

describe('arched window', () => {
  const arched = () => named(buildWall(wall([{ kind: 'arch', u0: 1, u1: 2, v0: 0.8, spring: 2.2 }])), 'window');
  const parts = () => arched()[0].children;

  it('fills an arched opening with one window', () => {
    expect(arched()).toHaveLength(1);
  });

  it('assembles casing, stool, apron, seven sash bars, the arched head and the glass', () => {
    expect(parts().map(p => p.name)).toEqual(['casing', ...Array<string>(11).fill('')]);
  });

  it('runs the casing around the arch down to the stool', () => {
    expect(extent(parts()[0])).toEqual([-1.095, 0.79, -1, 0.095, 2.795, -0.972]);
  });

  it('sets the stool under the opening and the apron under the stool, both wider than the opening', () => {
    const [, stool, apron] = parts();

    expect(extent(stool)).toEqual([-1.14, 0.76, -1.175, 0.14, 0.79, -0.925]);
    expect(extent(apron)).toEqual([-1.095, 0.67, -1, 0.095, 0.76, -0.98]);
  });

  it('sets the stiles, rails and mullions back in the reveal', () => {
    expect(parts().slice(3, 10).map(extent)).toEqual([
      [-1, 0.8, -1.143, -0.955, 2.2, -1.097], // left stile
      [-0.045, 0.8, -1.143, 0, 2.2, -1.097], // right stile
      [-1, 0.8, -1.143, 0, 0.845, -1.097], // bottom rail
      [-1, 2.146, -1.143, 0, 2.209, -1.097], // transom bar at the springline
      [-1, 1.964, -1.143, 0, 2.036, -1.097], // meeting rail
      [-0.518, 0.8, -1.143, -0.482, 2, -1.097], // center mullion
      [-0.514, 2, -1.143, -0.486, 2.2, -1.097], // transom mullion
    ]);
  });

  it('curves the sash head along the arch', () => {
    expect(extent(parts()[10])).toEqual([-1, 2.199, -1.142, 0, 2.7, -1.098]);
  });

  it('glazes the whole opening just behind the sash, without casting shadows', () => {
    const glass = parts()[11] as THREE.Mesh;

    expect(extent(glass)).toEqual([-1, 0.8, -1.125, 0, 2.7, -1.125]);
    expect(glass.material).toBe(materials().glass);
    expect(glass.castShadow).toBe(false);
  });

  it('glazes the rectangle below the springline and the half circle above it', () => {
    const glass = (parts()[11] as THREE.Mesh).geometry;
    const pos = glass.getAttribute('position');
    const index = glass.index;
    let area = 0;
    for (let i = 0; index && i < index.count; i += 3) {
      const [a, b, c] = [0, 1, 2].map(k => new THREE.Vector3().fromBufferAttribute(pos, index.getX(i + k)));
      area += new THREE.Triangle(a, b, c).getArea();
    }

    expect(area).toBeCloseTo(1 * 1.4 + (Math.PI * 0.5 ** 2) / 2, 2);
  });

  it('turns the stool, apron and sash bars with the wall', () => {
    const w: WallDef = {
      ...wall([{ kind: 'arch', u0: 1, u1: 2, v0: 0.8, spring: 2.2 }]),
      origin: new THREE.Vector3(3, 0, 1), u: new THREE.Vector3(0, 0, -1), n: new THREE.Vector3(1, 0, 0),
    };
    const [, stool, apron, , , bottomRail] = named(buildWall(w), 'window')[0].children;

    expect(extent(stool)).toEqual([2.825, 0.76, -1.14, 3.075, 0.79, 0.14]);
    expect(extent(apron)).toEqual([3, 0.67, -1.095, 3.02, 0.76, 0.095]);
    expect(extent(bottomRail)).toEqual([2.857, 0.8, -1, 2.903, 0.845, 0]);
  });

  it('builds the window trim from the palette trim', () => {
    expect(parts().slice(0, 11).every(p => (p as THREE.Mesh).material === materials().trim)).toBe(true);
  });
});
