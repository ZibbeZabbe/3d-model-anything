import simd

/// A room's floor outline (house x/z) and floor height, for checking a doorway connection.
struct RoomFootprint {
  /// One RoomPlan wall: `transform` is centred on the wall, its x axis runs along the wall.
  struct Wall {
    let transform: simd_float4x4
    let width: Float
    let height: Float
  }

  let outline: [SIMD2<Float>]
  let floorY: Float

  init(outline: [SIMD2<Float>], floorY: Float) {
    self.outline = outline
    self.floorY = floorY
  }

  /// Builds the outline from the wall end points, ordered around their centroid (RoomPlan
  /// rooms are close to convex), and the floor from the lowest wall bottom.
  ///
  /// # Arguments
  /// - `walls`: the room's walls in its session frame.
  /// - `placement`: session frame to house frame.
  init(walls: [Wall], placement: simd_float4x4) {
    var ends: [SIMD2<Float>] = []
    var floor = Float.infinity
    for wall in walls {
      let m = placement * wall.transform
      let center = SIMD3(m.columns.3.x, m.columns.3.y, m.columns.3.z)
      let along = simd_normalize(SIMD3(m.columns.0.x, m.columns.0.y, m.columns.0.z)) * wall.width / 2
      for end in [center - along, center + along] { ends.append(SIMD2(end.x, end.z)) }
      floor = min(floor, center.y - wall.height / 2)
    }
    let centroid = ends.reduce(SIMD2<Float>(repeating: 0), +) / Float(max(ends.count, 1))
    outline = ends.sorted { atan2($0.y - centroid.y, $0.x - centroid.x) < atan2($1.y - centroid.y, $1.x - centroid.x) }
    floorY = walls.isEmpty ? 0 : floor
  }

  /// Even-odd point-in-polygon test.
  func contains(_ p: SIMD2<Float>) -> Bool {
    var inside = false
    var j = outline.count - 1
    for i in outline.indices {
      let a = outline[i], b = outline[j]
      if (a.y > p.y) != (b.y > p.y), p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x { inside.toggle() }
      j = i
    }
    return inside
  }
}

/// Plausibility of a manual doorway connection, measured before it is saved: rooms on the two
/// sides of a doorway should not overlap, and their floors should meet at the same height.
/// A large overlap usually means the orientation toggle is wrong.
struct ConnectionCheck {
  enum Issue: Equatable { case overlap, floorStep }

  /// Above this share of the placed room lying inside the reference room, the placement is suspect.
  static let maxOverlap: Float = 0.1
  /// Above this floor height difference (meters), the placement is suspect.
  static let maxFloorStep: Float = 0.05
  /// Sampling step of the overlap estimate (meters).
  private static let sampleStep: Float = 0.05

  /// Share (0...1) of the placed room's floor that lies inside the reference room.
  let overlap: Float
  /// Absolute floor height difference, in meters.
  let floorStep: Float
  let issues: [Issue]

  init(placed: RoomFootprint, reference: RoomFootprint) {
    overlap = Self.overlap(of: placed, in: reference)
    floorStep = abs(placed.floorY - reference.floorY)
    var found: [Issue] = []
    if overlap > Self.maxOverlap { found.append(.overlap) }
    if floorStep > Self.maxFloorStep { found.append(.floorStep) }
    issues = found
  }

  private static func overlap(of placed: RoomFootprint, in reference: RoomFootprint) -> Float {
    guard let first = placed.outline.first else { return 0 }
    let lo = placed.outline.reduce(first) { simd_min($0, $1) }
    let hi = placed.outline.reduce(first) { simd_max($0, $1) }
    var inPlaced = 0, inBoth = 0
    var x = lo.x + sampleStep / 2
    while x < hi.x {
      var z = lo.y + sampleStep / 2
      while z < hi.y {
        let p = SIMD2(x, z)
        if placed.contains(p) {
          inPlaced += 1
          if reference.contains(p) { inBoth += 1 }
        }
        z += sampleStep
      }
      x += sampleStep
    }
    return inPlaced == 0 ? 0 : Float(inBoth) / Float(inPlaced)
  }
}
