/// A storey of the house, counted from the ground floor: 0 is the ground floor, 1 the floor above,
/// -1 the first basement. Set by the user on each room, since a storey is not something RoomPlan
/// measures.
struct Level: Hashable, Comparable {
  let number: Int

  init(_ number: Int) { self.number = number }

  static func < (a: Level, b: Level) -> Bool { a.number < b.number }

  var name: String {
    switch number {
    case 0: "Ground floor"
    case -1: "Basement"
    case ..<0: "Basement \(-number)"
    default: "\(number)\(Self.ordinalSuffix(number)) floor"
    }
  }

  private static func ordinalSuffix(_ n: Int) -> String {
    if (11...13).contains(n % 100) { return "th" }
    switch n % 10 {
    case 1: return "st"
    case 2: return "nd"
    case 3: return "rd"
    default: return "th"
    }
  }
}

/// Stored in house.json as the bare storey number.
extension Level: Codable {
  init(from decoder: Decoder) throws { number = try decoder.singleValueContainer().decode(Int.self) }

  func encode(to encoder: Encoder) throws {
    var container = encoder.singleValueContainer()
    try container.encode(number)
  }
}

extension HouseProject {
  /// The rooms on one level, in house order; `level` is nil for rooms not put on a level yet.
  struct LevelGroup {
    let level: Level?
    let rooms: [Room]
  }

  var roomsByLevel: [LevelGroup] {
    let levels = Set(rooms.compactMap(\.level)).sorted()
    let placed = levels.map { level in LevelGroup(level: level, rooms: rooms.filter { $0.level == level }) }
    let unplaced = rooms.filter { $0.level == nil }
    return placed + (unplaced.isEmpty ? [] : [LevelGroup(level: nil, rooms: unplaced)])
  }
}
