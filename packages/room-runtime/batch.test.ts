import * as THREE from 'three';
import { describe, expect, it } from 'vitest';
import { batchStatic } from './batch';

/** Characterization of the static draw-call batcher: what it merges today. */
// Phong, not Standard: separate MeshStandardMaterials never match today (see material matching).
const paint = (parameters: THREE.MeshPhongMaterialParameters = {}) => new THREE.MeshPhongMaterial({ color: '#808080', name: 'paint', ...parameters });
function cube(material: THREE.Material | THREE.Material[], at: [number, number, number] = [0, 0, 0]): THREE.Mesh {
  const m = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), material);
  m.position.set(...at);
  return m;
}
function scene(...children: THREE.Object3D[]) {
  const root = new THREE.Group();
  root.add(...children);
  return root;
}
const meshes = (o: THREE.Object3D) => {
  const out: THREE.Mesh[] = [];
  o.traverse(c => { if (c instanceof THREE.Mesh) out.push(c); });
  return out;
};
const batches = (o: THREE.Object3D) => meshes(o).filter(m => m.name.startsWith('batch:'));
const mm = (n: number) => Math.round(n * 1000) / 1000 + 0; // + 0 turns -0 into 0
const extent = (g: THREE.BufferGeometry) => {
  g.computeBoundingBox();
  const b = g.boundingBox ?? new THREE.Box3();
  return [...b.min.toArray(), ...b.max.toArray()].map(mm);
};
/** Batch two cubes that differ only by what `vary` does to the second one, and count the batches. */
function mergesWith(vary: (second: THREE.Mesh) => void) {
  const material = paint();
  const second = cube(material, [2, 0, 0]);
  vary(second);
  return batchStatic(scene(cube(material), second)).batches === 1;
}

describe('static batching', () => {
  it('merges static meshes that share a material into one mesh and reports the draw calls saved', () => {
    const material = paint();
    const root = scene(cube(material), cube(material, [2, 0, 0]));

    expect(batchStatic(root)).toEqual({ meshesBefore: 2, meshesAfter: 1, batches: 1 });
    expect(meshes(root)).toHaveLength(1);
  });

  it('names the batch after its material, and remembers how many meshes went in', () => {
    const material = paint();
    const root = scene(cube(material), cube(material, [2, 0, 0]), cube(material, [4, 0, 0]));
    batchStatic(root);
    const [batch] = batches(root);

    expect([batch.name, batch.material, batch.userData.batched]).toEqual(['batch:paint', material, 3]);
  });

  it('names the batch after the material type when the material has no name', () => {
    const material = new THREE.MeshBasicMaterial();
    const root = scene(cube(material), cube(material, [2, 0, 0]));
    batchStatic(root);

    expect(batches(root)[0].name).toBe('batch:MeshBasicMaterial');
  });

  it('bakes each mesh transform into the merged geometry', () => {
    const material = paint();
    const root = scene(cube(material), cube(material, [2, 0, 0]));
    batchStatic(root);

    expect(extent(batches(root)[0].geometry)).toEqual([-0.5, -0.5, -0.5, 2.5, 0.5, 0.5]);
  });

  it('computes the batch bounds for culling', () => {
    const material = paint();
    const root = scene(cube(material), cube(material, [2, 0, 0]));
    batchStatic(root);
    const { geometry } = batches(root)[0];

    expect([geometry.boundingBox, geometry.boundingSphere].every(b => b !== null)).toBe(true);
  });

  it('leaves a mesh alone when nothing shares its material', () => {
    const root = scene(cube(paint()), cube(paint({ color: '#ff0000' }), [2, 0, 0]));

    expect(batchStatic(root)).toEqual({ meshesBefore: 2, meshesAfter: 2, batches: 0 });
  });

  it('merges separate materials whose parameters are identical', () => {
    expect(batchStatic(scene(cube(paint()), cube(paint(), [2, 0, 0]))).batches).toBe(1);
  });

  it('keeps the batch flags of its meshes', () => {
    const material = paint();
    const a = cube(material), b = cube(material, [2, 0, 0]);
    for (const m of [a, b]) Object.assign(m, { castShadow: true, receiveShadow: false, renderOrder: 3 });
    const root = scene(a, b);
    batchStatic(root);
    const [batch] = batches(root);

    expect([batch.castShadow, batch.receiveShadow, batch.renderOrder]).toEqual([true, false, 3]);
  });

  it('flips the winding of a mirrored mesh so its faces still point outward', () => {
    const material = paint();
    const plain = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), material);
    const mirrored = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), material);
    mirrored.scale.x = -1;
    mirrored.position.x = 2;
    const root = scene(plain, mirrored);
    batchStatic(root);
    const g = batches(root)[0].geometry;
    const index = g.index;
    if (!index) throw new Error('batches are indexed');
    const normals = Array.from({ length: index.count / 3 }, (_, t) => {
      const [a, b, c] = [0, 1, 2].map(k => new THREE.Vector3().fromBufferAttribute(g.getAttribute('position'), index.getX(t * 3 + k)));
      return mm(b.sub(a).cross(c.sub(a)).normalize().z);
    });

    expect(normals).toEqual([1, 1, 1, 1]);
  });

  it('indexes the batch even when its meshes have no index', () => {
    const material = paint();
    const a = cube(material), b = cube(material, [2, 0, 0]);
    for (const m of [a, b]) m.geometry = m.geometry.toNonIndexed();
    const root = scene(a, b);
    batchStatic(root);

    expect(Array.from(batches(root)[0].geometry.index?.array ?? [])).toEqual(Array.from({ length: 72 }, (_, i) => i));
  });

  it('leaves the index of a mirrored mesh geometry intact for the meshes sharing it', () => {
    const material = paint();
    const shared = new THREE.PlaneGeometry(1, 1);
    const before = Array.from(shared.index?.array ?? []);
    const mirrored = new THREE.Mesh(shared, material);
    mirrored.scale.x = -1;
    const kept = new THREE.Mesh(shared, material);
    kept.userData.noMerge = true;
    batchStatic(scene(mirrored, new THREE.Mesh(new THREE.PlaneGeometry(1, 1), material), kept));

    expect(Array.from(shared.index?.array ?? [])).toEqual(before);
  });
});

describe('static batching exclusions', () => {
  it.each([
    ['transparent materials', (m: THREE.Mesh) => {
      const glass = paint();
      glass.transparent = true;
      m.material = glass;
    }],
    ['meshes with children', (m: THREE.Mesh) => m.add(new THREE.Object3D())],
    ['meshes with a custom onBeforeRender', (m: THREE.Mesh) => { m.onBeforeRender = () => undefined; }],
    ['meshes with a custom draw range', (m: THREE.Mesh) => m.geometry.setDrawRange(0, 6)],
    ['meshes with a draw range that does not start at zero', (m: THREE.Mesh) => m.geometry.setDrawRange(6, Infinity)],
    ['meshes with morph targets', (m: THREE.Mesh) => { m.morphTargetInfluences = [0]; }],
    ['geometries with morph attributes', (m: THREE.Mesh) => { m.geometry.morphAttributes.position = [m.geometry.getAttribute('position') as THREE.BufferAttribute]; }],
    ['nodes marked noMerge', (m: THREE.Mesh) => { m.userData.noMerge = true; }],
  ] as [string, (m: THREE.Mesh) => void][])('never merges %s', (_, exclude) => {
    const material = paint();
    const a = cube(material), b = cube(material, [2, 0, 0]);
    exclude(a);
    exclude(b);

    expect(batchStatic(scene(a, b)).batches).toBe(0);
  });

  it('never merges multi-material meshes', () => {
    const material = paint();

    expect(batchStatic(scene(cube([material]), cube([material], [2, 0, 0]))).batches).toBe(0);
  });

  it('never merges instanced meshes', () => {
    const material = paint();
    const instanced = () => new THREE.InstancedMesh(new THREE.BoxGeometry(), material, 2);

    expect(batchStatic(scene(instanced(), instanced())).batches).toBe(0);
  });

  it('never merges skinned meshes', () => {
    const material = paint();
    const skinned = () => new THREE.SkinnedMesh(new THREE.BoxGeometry(), material);

    expect(batchStatic(scene(skinned(), skinned())).batches).toBe(0);
  });

  it('never merges a mesh without positions', () => {
    const material = paint();
    const empty = () => new THREE.Mesh(new THREE.BufferGeometry(), material);

    expect(batchStatic(scene(empty(), empty())).batches).toBe(0);
  });

  it('skips everything under a noMerge node, without counting it', () => {
    const material = paint();
    const hold = new THREE.Group();
    hold.userData.noMerge = true;
    hold.add(cube(material), cube(material));

    expect(batchStatic(scene(hold))).toEqual({ meshesBefore: 0, meshesAfter: 0, batches: 0 });
  });

  it('merges the root itself even when it is marked noMerge', () => {
    const material = paint();
    const root = scene(cube(material), cube(material, [2, 0, 0]));
    root.userData.noMerge = true;

    expect(batchStatic(root).batches).toBe(1);
  });

  it('skips hidden subtrees, without counting them', () => {
    const material = paint();
    const hidden = new THREE.Group();
    hidden.visible = false;
    hidden.add(cube(material), cube(material));

    expect(batchStatic(scene(hidden, cube(material)))).toEqual({ meshesBefore: 1, meshesAfter: 1, batches: 0 });
  });
});

describe('static batching keys', () => {
  it.each([
    ['shadow casting', (m: THREE.Mesh) => { m.castShadow = true; }],
    ['shadow receiving', (m: THREE.Mesh) => { m.receiveShadow = true; }],
    ['render order', (m: THREE.Mesh) => { m.renderOrder = 1; }],
    ['layers', (m: THREE.Mesh) => m.layers.set(2)],
    ['frustum culling', (m: THREE.Mesh) => { m.frustumCulled = false; }],
    ['physics class', (m: THREE.Mesh) => { m.userData.physics = { type: 'none' }; }],
  ] as [string, (m: THREE.Mesh) => void][])('keeps meshes apart that differ in %s', (_, vary) => {
    expect(mergesWith(vary)).toBe(false);
  });

  const attribute = (itemSize: number) => new THREE.Float32BufferAttribute(new Float32Array(24 * itemSize), itemSize);
  const varyAttributes: [string, (m: THREE.Mesh) => void][] = [
    ['without normals', m => m.geometry.deleteAttribute('normal')],
    ['without uvs', m => m.geometry.deleteAttribute('uv')],
    ['with a second uv set', m => m.geometry.setAttribute('uv1', attribute(2))],
    ['with vertex colours', m => m.geometry.setAttribute('color', attribute(3))],
    ['with tangents', m => m.geometry.setAttribute('tangent', attribute(4))],
  ];

  it.each(varyAttributes)('keeps a mesh %s apart from meshes that differ, while those still merge', (_, vary) => {
    const material = paint();
    const odd = cube(material, [4, 0, 0]);
    vary(odd);

    expect(batchStatic(scene(cube(material), cube(material, [2, 0, 0]), odd)).batches).toBe(1);
  });

  it('keeps meshes apart whose attribute has a different item size', () => {
    const material = paint();
    const [a, b, odd] = [cube(material), cube(material, [2, 0, 0]), cube(material, [4, 0, 0])];
    a.geometry.setAttribute('color', attribute(3));
    b.geometry.setAttribute('color', attribute(3));
    odd.geometry.setAttribute('color', attribute(4));

    expect(batchStatic(scene(a, b, odd)).batches).toBe(1);
  });

  it.each(['normal', 'uv', 'uv1', 'color', 'tangent'])('carries the %s attribute into the batch', (name) => {
    const material = paint();
    const a = cube(material), b = cube(material, [2, 0, 0]);
    const sizes: Record<string, number> = { normal: 3, uv: 2, uv1: 2, color: 3, tangent: 4 };
    for (const m of [a, b]) if (!m.geometry.getAttribute(name)) m.geometry.setAttribute(name, attribute(sizes[name]));
    const root = scene(a, b);
    batchStatic(root);

    expect(batches(root)[0].geometry.getAttribute(name)?.count).toBe(48);
  });

  it('merges into a single draw without material groups', () => {
    const material = paint();
    const root = scene(cube(material), cube(material, [2, 0, 0]));
    batchStatic(root);

    expect(batches(root)[0].geometry.groups).toEqual([]);
  });

  it('ignores attributes outside the standard set when matching meshes', () => {
    expect(mergesWith(m => m.geometry.setAttribute('weight', new THREE.Float32BufferAttribute(new Float32Array(24), 1)))).toBe(true);
  });

  it('marks a batch of physics-free meshes as physics-free', () => {
    const material = paint();
    const a = cube(material), b = cube(material, [2, 0, 0]);
    for (const m of [a, b]) m.userData.physics = { type: 'none' };
    const root = scene(a, b);
    batchStatic(root);

    expect(batches(root)[0].userData.physics).toEqual({ type: 'none' });
  });

  it('treats meshes under a physics-free node as physics-free', () => {
    const material = paint();
    const shelf = new THREE.Group();
    shelf.userData.physics = { type: 'none' };
    shelf.add(cube(material), cube(material, [2, 0, 0]));
    const root = scene(shelf);
    batchStatic(root);

    expect(batches(root)[0].userData.physics).toEqual({ type: 'none' });
  });

  it('leaves the physics of an ordinary batch unset', () => {
    const material = paint();
    const root = scene(cube(material), cube(material, [2, 0, 0]));
    batchStatic(root);

    expect(batches(root)[0].userData.physics).toBeUndefined();
  });
});

describe('static batching visibility roots', () => {
  it('never merges meshes across visibility roots, and adds each batch to its own root', () => {
    const material = paint();
    const north = scene(cube(material), cube(material, [2, 0, 0])), south = scene(cube(material), cube(material, [2, 0, 0]));
    const root = scene(north, south);

    expect(batchStatic(root, [north, south]).batches).toBe(2);
    expect([north, south].map(r => r.children.map(c => c.name))).toEqual([['batch:paint'], ['batch:paint']]);
  });

  it('bakes a batch in the local space of its root', () => {
    const material = paint();
    const wall = scene(cube(material), cube(material, [2, 0, 0]));
    wall.position.set(10, 0, 0);
    const root = scene(wall);
    batchStatic(root, [wall]);

    expect(extent(batches(root)[0].geometry)).toEqual([-0.5, -0.5, -0.5, 2.5, 0.5, 0.5]);
  });
});

describe('static batching of dynamic bodies', () => {
  function body(shape = 'convex') {
    const material = paint();
    const b = scene(cube(material), cube(material, [0, 1, 0]));
    b.userData.physics = { type: 'dynamic', shape };
    return { body: b, material };
  }

  it('merges the meshes of a dynamic body only among themselves, inside the body', () => {
    const { body: crate, material } = body();
    const root = scene(crate, cube(material, [5, 0, 0]), cube(material, [7, 0, 0]));

    expect(batchStatic(root).batches).toBe(2);
    expect(crate.children.map(c => c.name)).toEqual(['batch:paint']);
  });

  it('leaves a compound dynamic body untouched, one hull per mesh', () => {
    const { body: crate } = body('compound');

    expect(batchStatic(scene(crate))).toEqual({ meshesBefore: 0, meshesAfter: 0, batches: 0 });
  });

  it('merges dynamic bodies with everything else when nothing will move', () => {
    const { body: crate, material } = body('compound');
    const root = scene(crate, cube(material, [5, 0, 0]));

    expect(batchStatic(root, [], { mergeDynamic: true })).toEqual({ meshesBefore: 3, meshesAfter: 1, batches: 1 });
    expect(root.children.map(c => c.name)).toContain('batch:paint');
  });

  it('treats the root as a plain node even when it is a dynamic body', () => {
    const { body: crate } = body('compound');

    expect(batchStatic(crate).batches).toBe(1);
  });
});

describe('material matching', () => {
  const merges = (a: THREE.Material, b: THREE.Material) => batchStatic(scene(cube(a), cube(b, [2, 0, 0]))).batches === 1;

  it('ignores names, ids and user data', () => {
    const a = paint(), b = paint();
    b.name = 'other';
    b.userData.note = 'x';

    expect(merges(a, b)).toBe(true);
  });

  it('tells colours apart by hue', () => {
    expect(merges(paint({ color: '#ff0000' }), paint({ color: '#00ff00' }))).toBe(false);
  });

  it('ignores the material version, bumped by needsUpdate', () => {
    const bumped = paint();
    bumped.needsUpdate = true;

    expect(merges(paint(), bumped)).toBe(true);
  });

  it('matches equal array parameters', () => {
    expect(merges(Object.assign(paint(), { clippingPlanes: [] }), Object.assign(paint(), { clippingPlanes: [] }))).toBe(true);
  });

  it('tells colours apart', () => {
    expect(merges(paint(), paint({ emissive: '#010101' }))).toBe(false);
  });

  it('tells numeric, boolean and vector parameters apart', () => {
    expect(merges(paint(), paint({ shininess: 5 }))).toBe(false);
    expect(merges(paint(), paint({ wireframe: true }))).toBe(false);
    expect(merges(paint(), paint({ normalScale: new THREE.Vector2(2, 2) }))).toBe(false);
  });

  it('tells array parameters apart', () => {
    expect(merges(paint(), Object.assign(paint(), { clippingPlanes: [new THREE.Plane()] }))).toBe(false);
  });

  it('tells alpha test thresholds apart, since a cutout discards fragments', () => {
    expect(merges(paint(), paint({ alphaTest: 0.5 }))).toBe(false);
  });

  it('tells the material types apart', () => {
    expect(merges(new THREE.MeshLambertMaterial(), new THREE.MeshPhongMaterial())).toBe(false);
  });

  it('matches textures that share an image source and transform', () => {
    const source = new THREE.Texture();
    expect(merges(paint({ map: source.clone() }), paint({ map: source.clone() }))).toBe(true);
  });

  it('tells textures apart by image source', () => {
    expect(merges(paint({ map: new THREE.Texture() }), paint({ map: new THREE.Texture() }))).toBe(false);
  });

  it('tells textures apart by repeat', () => {
    const source = new THREE.Texture();
    const repeated = source.clone();
    repeated.repeat.set(2, 2);

    expect(merges(paint({ map: source.clone() }), paint({ map: repeated }))).toBe(false);
  });

  // Pins a gap, not an intent: the `defines` object of Standard and Physical materials is an
  // unknown object-valued parameter, so their fingerprint falls back to the uuid.
  it('does not match separate but identical standard materials', () => {
    expect(merges(new THREE.MeshStandardMaterial(), new THREE.MeshStandardMaterial())).toBe(false);
  });

  it('merges a standard material with itself', () => {
    const shared = new THREE.MeshStandardMaterial();

    expect(merges(shared, shared)).toBe(true);
  });

  it('only matches a shader material with itself', () => {
    const shader = () => new THREE.ShaderMaterial({ vertexShader: 'void main() {}', fragmentShader: 'void main() {}' });

    expect(merges(shader(), shader())).toBe(false);
  });

  it('only matches a material with a custom compile hook with itself', () => {
    const custom = () => {
      const m = paint();
      m.onBeforeCompile = () => undefined;
      return m;
    };

    expect(merges(custom(), custom())).toBe(false);
  });

  it('merges a shader material with itself', () => {
    const shader = new THREE.ShaderMaterial({ vertexShader: 'void main() {}', fragmentShader: 'void main() {}' });

    expect(merges(shader, shader)).toBe(true);
  });
});
