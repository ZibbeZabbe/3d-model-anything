import XCTest
@testable import HouseCapture

final class LevelTests: XCTestCase {
  func testALevelIsNamedAfterItsStoreyAboveOrBelowTheGroundFloor() {
    let names = [-2: "Basement 2", -1: "Basement", 0: "Ground floor", 1: "1st floor", 2: "2nd floor", 3: "3rd floor", 4: "4th floor", 11: "11th floor", 12: "12th floor", 21: "21st floor"]

    for (number, name) in names {
      XCTAssertEqual(Level(number).name, name, "level \(number)")
    }
  }
}

final class RoomLevelCodingTests: XCTestCase {
  private func room(_ extra: String) throws -> HouseProject.Room {
    try JSONDecoder().decode(HouseProject.Room.self, from: Data(#"{"id":"r1","name":"Bedroom","zone":"area-1","history":[]\#(extra)}"#.utf8))
  }

  func testARoomSavedBeforeLevelsExistedHasNoLevel() throws {
    XCTAssertNil(try room("").level)
  }

  func testARoomLevelIsStoredAsItsNumber() throws {
    var bedroom = try room("")
    bedroom.level = Level(1)

    let json = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(bedroom)) as? [String: Any])

    XCTAssertEqual(json["level"] as? Int, 1)
    XCTAssertEqual(try room(#","level":-1"#).level, Level(-1))
  }
}

final class RoomsByLevelTests: XCTestCase {
  private func room(_ id: String, _ level: Int?) -> HouseProject.Room {
    .init(id: id, name: id, zone: "area-1", level: level.map(Level.init))
  }

  private func house(_ rooms: [HouseProject.Room]) -> HouseProject {
    HouseProject(id: "h", name: "House", createdAt: Date(timeIntervalSince1970: 0), rooms: rooms)
  }

  func testWithoutAnyLevelAllRoomsFormOneUnnamedGroup() {
    let groups = house([room("kitchen", nil), room("bathroom", nil)]).roomsByLevel

    XCTAssertEqual(groups.map(\.level), [nil])
    XCTAssertEqual(groups.first?.rooms.map(\.id), ["kitchen", "bathroom"])
  }

  func testLevelsRunFromTheLowestUpWithRoomsWithoutALevelLast() {
    let groups = house([room("bedroom", 1), room("hall", nil), room("kitchen", 0), room("cellar", -1), room("office", 1)]).roomsByLevel

    XCTAssertEqual(groups.map(\.level), [Level(-1), Level(0), Level(1), nil])
    XCTAssertEqual(groups.map { $0.rooms.map(\.id) }, [["cellar"], ["kitchen"], ["bedroom", "office"], ["hall"]])
  }
}
