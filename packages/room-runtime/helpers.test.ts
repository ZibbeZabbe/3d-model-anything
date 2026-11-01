import * as THREE from 'three';
import { describe, expect, it } from 'vitest';
import { arc, box, boxSpan, boxUV, cushion, cylinder, lathe, mesh, pillow, place, sphere, sweep, tube } from './helpers';

/** Characterization of the modelling helpers: what they build today. */
const material = new THREE.MeshBasicMaterial();
const mm = (n: number) => Math.round(n * 1000) / 1000 + 0; // + 0 turns -0 into 0
/** World-space bounding box as [minX, minY, minZ, maxX, maxY, maxZ], rounded to the millimetre. */
const extent = (o: THREE.Object3D) => {
  const b = new THREE.Box3().setFromObject(o);
  return [...b.min.toArray(), ...b.max.toArray()].map(mm);
};
const vertex = (g: THREE.BufferGeometry, i: number) => new THREE.Vector3().fromBufferAttribute(g.getAttribute('position'), i).toArray().map(mm);
const uvAt = (g: THREE.BufferGeometry, i: number) => [g.getAttribute('uv').getX(i), g.getAttribute('uv').getY(i)].map(mm);
const vertexCount = (g: THREE.BufferGeometry) => g.getAttribute('position').count;
const triangleCount = (g: THREE.BufferGeometry) => (g.index?.count ?? 0) / 3;
/** Unit normal of triangle t, from its winding. */
function faceNormal(g: THREE.BufferGeometry, t: number) {
  const index = g.index;
  if (!index) throw new Error('sweep geometry is indexed');
  const [a, b, c] = [0, 1, 2].map(k => new THREE.Vector3().fromBufferAttribute(g.getAttribute('position'), index.getX(t * 3 + k)));
  return b.sub(a).cross(c.sub(a)).normalize().toArray().map(mm);
}

describe('mesh', () => {
  it('casts and receives shadows', () => {
    const m = mesh(new THREE.BoxGeometry(), material);

    expect([m.castShadow, m.receiveShadow]).toEqual([true, true]);
  });

  it('names the mesh when a name is given', () => {
    expect(mesh(new THREE.BoxGeometry(), material, 'leg').name).toBe('leg');
  });

  it('leaves the mesh unnamed by default', () => {
    expect(mesh(new THREE.BoxGeometry(), material).name).toBe('');
  });
});

describe('place', () => {
  it('moves the object and turns it about the vertical axis', () => {
    const o = place(new THREE.Object3D(), [1, 2, 3], 0.5);

    expect([...o.position.toArray(), o.rotation.y]).toEqual([1, 2, 3, 0.5]);
  });

  it('resets the heading when none is given', () => {
    const o = new THREE.Object3D();
    o.rotation.y = 1;

    expect(place(o, [0, 0, 0]).rotation.y).toBe(0);
  });
});

describe('box', () => {
  it('builds a box of the given size around the given center', () => {
    expect(extent(box([1, 2, 3], [10, 20, 30], material))).toEqual([9.5, 19, 28.5, 10.5, 21, 31.5]);
  });

  it('maps its UVs in meters, scaled by the UV scale', () => {
    const b = box([2, 2, 2], [0, 0, 0], material, 0.5);
    // vertex 0 is the +x face corner (1, 1, 1): u, v come from (z, y)

    expect(uvAt(b.geometry, 0)).toEqual([0.5, 0.5]);
  });

  it('spans a box between its min and max corners', () => {
    expect(extent(boxSpan([1, 2, 3], [2, 4, 7], material))).toEqual([1, 2, 3, 2, 4, 7]);
  });
});

describe('cushion', () => {
  // RoundedBoxGeometry stores its radius in parameters, but its typings only declare the box ones.
  const roundingRadius = (c: THREE.Mesh) => {
    const { parameters } = c.geometry as THREE.BoxGeometry;
    return 'radius' in parameters && typeof parameters.radius === 'number' ? parameters.radius : NaN;
  };
  it('builds a rounded block of the given size around the given center', () => {
    expect(extent(cushion([1, 0.2, 0.5], [0, 1, 0], 0.05, material))).toEqual([-0.5, 0.9, -0.25, 0.5, 1.1, 0.25]);
  });

  it('keeps the block size when the radius exceeds half its thinnest side', () => {
    expect(extent(cushion([1, 0.2, 0.5], [0, 1, 0], 5, material))).toEqual([-0.5, 0.9, -0.25, 0.5, 1.1, 0.25]);
  });

  it('rounds the edges with the given radius', () => {
    expect(roundingRadius(cushion([1, 0.2, 0.5], [0, 0, 0], 0.05, material))).toBe(0.05);
  });

  it.each([
    [[0.2, 1, 0.5]],
    [[1, 0.2, 0.5]],
    [[1, 0.5, 0.2]],
  ] as [[number, number, number]][])('clamps the radius just under half the thinnest side of %j', (size) => {
    expect(mm(roundingRadius(cushion(size, [0, 0, 0], 5, material)))).toBe(0.099);
  });

  it('gives the cushion box-projected UVs in meters', () => {
    const c = cushion([1, 0.2, 0.5], [0, 0, 0], 0.05, material);
    const top = Array.from({ length: vertexCount(c.geometry) }, (_, i) => i).find(i => vertex(c.geometry, i)[1] === 0.1 && c.geometry.getAttribute('normal').getY(i) > 0.99);
    if (top === undefined) throw new Error('the cushion has a flat top');
    const [x, , z] = vertex(c.geometry, top);

    expect(uvAt(c.geometry, top)).toEqual([x, z]);
  });
});

describe('box UV projection', () => {
  /** One vertex per normal, at position (1, 2, 3). */
  function points(normals: [number, number, number][]) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(normals.flatMap(() => [1, 2, 3]), 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(normals.flat(), 3));
    return g;
  }
  const uvs = (g: THREE.BufferGeometry) => Array.from({ length: vertexCount(g) }, (_, i) => uvAt(g, i));

  it('projects each vertex along the dominant axis of its normal', () => {
    // x-facing: (z, y); y-facing: (x, z); z-facing: (x, y)
    expect(uvs(boxUV(points([[1, 0, 0], [0, -1, 0], [0, 0, 1]])))).toEqual([[3, 2], [1, 3], [1, 2]]);
  });

  it('breaks ties toward x, then toward y', () => {
    expect(uvs(boxUV(points([[1, 1, 1], [1, 1, 0], [0, 1, 1], [1, 0, 1]])))).toEqual([[3, 2], [3, 2], [1, 3], [3, 2]]);
  });

  it('scales the projected coordinates', () => {
    expect(uvs(boxUV(points([[0, 0, -1]]), 2))).toEqual([[2, 4]]);
  });
});

describe('sweep', () => {
  const up = new THREE.Vector3(0, 0, 1);
  const line = [new THREE.Vector3(0, 0, 0), new THREE.Vector3(2, 0, 0)];
  const strip: [number, number][] = [[0, 0], [0.1, 0], [0.1, 0.2]];

  it('offsets the profile s to the left of travel and t along the plane normal', () => {
    const g = sweep(strip, line, up, { caps: false });

    expect([0, 1, 2, 3, 4, 5].map(i => vertex(g, i))).toEqual([
      [0, 0, 0], [0, 0.1, 0], [0, 0.1, 0.2],
      [2, 0, 0], [2, 0.1, 0], [2, 0.1, 0.2],
    ]);
  });

  it('normalizes the plane normal', () => {
    const g = sweep(strip, line, new THREE.Vector3(0, 0, 5), { caps: false });

    expect(vertex(g, 2)).toEqual([0, 0.1, 0.2]);
  });

  it('maps u to the distance along the path and v to the distance along the profile', () => {
    const g = sweep(strip, line, up, { caps: false });

    expect([0, 1, 2, 5].map(i => uvAt(g, i))).toEqual([[0, 0], [0, 0.1], [0, 0.3], [2, 0.3]]);
  });

  it('measures v along the profile whatever its offset from the path', () => {
    const g = sweep([[0, 0.1], [0, 0.3]], line, up, { caps: false });

    expect(uvAt(g, 1)).toEqual([0, 0.2]);
  });

  it('keeps counting u along the path across segments', () => {
    const g = sweep(strip, [...line, new THREE.Vector3(2, 3, 0)], up, { caps: false });

    expect(uvAt(g, 9)).toEqual([5, 0]);
  });

  it('winds the faces so an edge rising along the plane normal faces right of travel', () => {
    const g = sweep([[0, 0], [0, 0.2]], line, up, { caps: false });

    expect(faceNormal(g, 0)).toEqual([0, -1, 0]);
    expect(faceNormal(g, 1)).toEqual([0, -1, 0]);
  });

  it('winds every side face of every segment toward the outside of the profile', () => {
    const corner = [new THREE.Vector3(0, 0, 0), new THREE.Vector3(2, 0, 0), new THREE.Vector3(2, 2, 0)];
    const g = sweep(strip, corner, up, { caps: false });

    // per segment: the flat edge faces up, the rising edge faces right of travel
    expect(Array.from({ length: 8 }, (_, t) => faceNormal(g, t))).toEqual([
      [0, 0, 1], [0, 0, 1], [0, -1, 0], [0, -1, 0],
      [0, 0, 1], [0, 0, 1], [1, 0, 0], [1, 0, 0],
    ]);
  });

  it('miters a corner so the profile keeps its width on both legs', () => {
    const corner = [new THREE.Vector3(0, 0, 0), new THREE.Vector3(1, 0, 0), new THREE.Vector3(1, 1, 0)];
    const g = sweep([[0, 0], [0.1, 0]], corner, up, { caps: false });

    // second segment starts on the corner ring: profile point s = 0.1 sits on the inner miter
    expect(vertex(g, 1)).toEqual([0, 0.1, 0]);
    expect(vertex(g, 3)).toEqual([0.9, 0.1, 0]);
    expect(vertex(g, 5)).toEqual([0.9, 0.1, 0]);
    expect(vertex(g, 7)).toEqual([0.9, 1, 0]);
  });

  it('limits the miter on a hairpin turn to five times the profile offset', () => {
    const hairpin = [new THREE.Vector3(0, 0, 0), new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 0.1, 0)];
    const g = sweep([[0, 0], [0.1, 0]], hairpin, up, { caps: false });
    const [x, y] = vertex(g, 3);

    expect(mm(Math.hypot(x - 1, y))).toBe(0.5);
  });

  it('caps both ends of an open sweep with the triangulated profile', () => {
    const g = sweep(strip, line, up);

    // 1 segment: 2 rings of 3 + 2 caps of 3 vertices; 4 side + 2 cap triangles
    expect([vertexCount(g), triangleCount(g)]).toEqual([12, 6]);
  });

  it('builds each cap from the ring at its own end', () => {
    const g = sweep([[0, 0], [0.1, 0], [0.1, 0.1], [0, 0.1]], line, up);
    const index = g.index;
    const capX = (t: number) => [0, 1, 2].map(k => vertex(g, index?.getX(t * 3 + k) ?? -1)[0]);

    // 3 profile edges x 2 side triangles, then 2 triangles per cap
    expect([6, 7, 8, 9].map(capX)).toEqual([[0, 0, 0], [0, 0, 0], [2, 2, 2], [2, 2, 2]]);
  });

  it('turns the start cap against the travel and the end cap along it', () => {
    const g = sweep(strip, line, up);

    expect(faceNormal(g, 4)).toEqual([-1, 0, 0]);
    expect(faceNormal(g, 5)).toEqual([1, 0, 0]);
  });

  it('gives the cap vertices zero UVs', () => {
    expect(uvAt(sweep(strip, line, up), 8)).toEqual([0, 0]);
  });

  it('leaves the ends open when caps are turned off', () => {
    expect(triangleCount(sweep(strip, line, up, { caps: false }))).toBe(4);
  });

  it('joins the last point back to the first on a closed sweep, without caps', () => {
    const square = [new THREE.Vector3(0, 0, 0), new THREE.Vector3(1, 0, 0), new THREE.Vector3(1, 1, 0), new THREE.Vector3(0, 1, 0)];
    const g = sweep([[0, 0], [0.1, 0]], square, up, { closed: true });

    // 4 segments x 1 profile edge x 2 triangles
    expect(triangleCount(g)).toBe(8);
    // the first ring is mitered too: the closing segment meets the first one at a corner
    expect(vertex(g, 1)).toEqual([0.1, 0.1, 0]);
  });

  it('computes vertex normals', () => {
    expect(sweep(strip, line, up).getAttribute('normal')).toBeDefined();
  });
});

describe('lathe', () => {
  it('turns the [radius, y] profile about the vertical axis', () => {
    expect(extent(lathe([[0.5, 0], [0.5, 1]], material))).toEqual([-0.5, 0, -0.5, 0.5, 1, 0.5]);
  });

  it('uses 32 segments by default', () => {
    // (segments + 1) columns x profile points
    expect(vertexCount(lathe([[0.5, 0], [0.5, 1]], material).geometry)).toBe(66);
  });

  it('uses the given number of segments', () => {
    expect(vertexCount(lathe([[0.5, 0], [0.5, 1]], material, 8).geometry)).toBe(18);
  });
});

describe('tube', () => {
  it('runs a tube of the given radius through the points', () => {
    expect(extent(tube([[0, 0, 0], [1, 0, 0], [2, 0, 0]], 0.1, material))).toEqual([0, -0.1, -0.1, 2, 0.1, 0.1]);
  });

  it('uses 32 segments along the tube and 8 around it by default', () => {
    expect(vertexCount(tube([[0, 0, 0], [1, 0, 0]], 0.1, material).geometry)).toBe(33 * 9);
  });

  it('uses the given number of segments along the tube', () => {
    expect(vertexCount(tube([[0, 0, 0], [1, 0, 0]], 0.1, material, 4).geometry)).toBe(5 * 9);
  });
});

describe('cylinder', () => {
  it('stands a cylinder of the given radius and height around the given center', () => {
    expect(extent(cylinder(0.5, 2, [0, 1, 0], material))).toEqual([-0.5, 0, -0.5, 0.5, 2, 0.5]);
  });

  it('tapers to a different bottom radius when given one', () => {
    const geo = cylinder(0.1, 2, [0, 0, 0], material, 24, 0.5).geometry as THREE.CylinderGeometry;

    expect([geo.parameters.radiusTop, geo.parameters.radiusBottom]).toEqual([0.1, 0.5]);
  });

  it('uses 24 radial segments by default', () => {
    expect((cylinder(0.5, 2, [0, 0, 0], material).geometry as THREE.CylinderGeometry).parameters.radialSegments).toBe(24);
  });
});

describe('sphere', () => {
  it('places a sphere of the given radius, stretched by the given scale', () => {
    expect(extent(sphere(0.5, [1, 2, 3], material, [2, 1, 1]))).toEqual([0, 1.5, 2.5, 2, 2.5, 3.5]);
  });

  it('keeps the sphere round by default', () => {
    expect(sphere(0.5, [0, 0, 0], material).scale.toArray()).toEqual([1, 1, 1]);
  });
});

describe('arc', () => {
  it('samples steps + 1 points from the start angle to the end angle', () => {
    expect(arc(1, 2, 0.5, 0, Math.PI / 2, 2).map(p => p.map(mm))).toEqual([[1.5, 2], [1.354, 2.354], [1, 2.5]]);
  });

  it('samples six steps by default', () => {
    expect(arc(0, 0, 1, 0, Math.PI)).toHaveLength(7);
  });
});

describe('pillow', () => {
  const VOLUME = 0.011607; // m3, pinned from the current shape (the inscribed ellipsoid holds 0.0126)
  const size: [number, number, number] = [0.5, 0.4, 0.12];
  const shape = () => pillow(size, material).geometry;
  const positions = (g: THREE.BufferGeometry) => Array.from({ length: vertexCount(g) }, (_, i) => vertex(g, i));

  it('fills its footprint, bulging 4% at the seam, and its full thickness', () => {
    expect(extent(pillow(size, material))).toEqual([-0.26, -0.208, -0.06, 0.26, 0.208, 0.06]);
  });

  it('is full thickness in the middle and thin at the seam', () => {
    const points = positions(shape());
    const middle = Math.max(...points.filter(([x, y]) => x === 0 && y === 0).map(([, , z]) => z));
    const nearSeam = Math.max(...points.filter(([x]) => Math.abs(x) > 0.24).map(([, , z]) => Math.abs(z)));

    expect(middle).toBe(0.06);
    expect(nearSeam).toBeLessThan(0.03);
  });

  it('pokes its corners out past the inscribed ellipse', () => {
    const corners = positions(shape()).map(([x, y]) => Math.hypot(x / 0.25, y / 0.2));

    expect(Math.max(...corners)).toBeGreaterThan(Math.SQRT2);
  });

  it('holds a pinned volume of filling', () => {
    const g = shape();
    const index = g.index;
    if (!index) throw new Error('the pillow geometry is indexed');
    let volume = 0;
    for (let i = 0; i < index.count; i += 3) {
      const [a, b, c] = [0, 1, 2].map(k => new THREE.Vector3().fromBufferAttribute(g.getAttribute('position'), index.getX(i + k)));
      volume += a.dot(b.cross(c)) / 6; // signed tetrahedron volume against the origin
    }

    expect(Math.abs(volume)).toBeCloseTo(VOLUME, 6);
  });

  it('projects the pillow UVs in meters from its deformed shape', () => {
    const g = shape();
    const normal = g.getAttribute('normal');
    const front = Array.from({ length: vertexCount(g) }, (_, i) => i).filter(i => normal.getZ(i) > 0.9).slice(0, 20);

    expect(front.map(i => uvAt(g, i))).toEqual(front.map(i => vertex(g, i).slice(0, 2)));
  });

  it('recomputes the vertex normals after deforming the sphere', () => {
    const g = shape();
    const expected = g.clone();
    expected.computeVertexNormals();

    expect(Array.from(g.getAttribute('normal').array)).toEqual(Array.from(expected.getAttribute('normal').array));
  });
});
