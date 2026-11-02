import XCTest
@testable import HouseCapture

@MainActor
final class RoomLevelAssignmentTests: XCTestCase {
  private var house: HouseProject!

  override func setUpWithError() throws {
    house = try HouseProject.create(name: "Levels test \(UUID())")
    house.rooms = [.init(id: "bedroom", name: "Bedroom", zone: "area-1"), .init(id: "kitchen", name: "Kitchen", zone: "area-1")]
    try house.save()
  }

  override func tearDownWithError() throws {
    try? FileManager.default.removeItem(at: house.url)
  }

  func testPuttingARoomOnALevelIsSavedForThatRoomOnly() throws {
    try HouseProject.setRoomLevel(houseID: house.id, roomID: "bedroom", level: Level(1))

    let saved = try HouseProject.load(id: house.id)
    XCTAssertEqual(saved.rooms.map(\.level), [Level(1), nil])
  }

  func testARoomCanBeTakenOffItsLevel() throws {
    try HouseProject.setRoomLevel(houseID: house.id, roomID: "bedroom", level: Level(1))

    try HouseProject.setRoomLevel(houseID: house.id, roomID: "bedroom", level: nil)

    XCTAssertNil(try HouseProject.load(id: house.id).rooms.first?.level)
  }
}
