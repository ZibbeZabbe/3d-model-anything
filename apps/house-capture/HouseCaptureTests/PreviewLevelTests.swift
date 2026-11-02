import XCTest
@testable import HouseCapture

@MainActor
final class PreviewLevelTests: XCTestCase {
  private func room(_ index: Int, _ name: String, _ level: Int?) -> PreviewRoom {
    PreviewRoom(session: 0, index: index, name: name, mesh: URL(fileURLWithPath: "/dev/null"), usdz: nil, level: level.map(Level.init))
  }

  private func model() -> PreviewModel {
    let rooms = [room(0, "Kitchen", 0), room(1, "Bedroom", 1), room(2, "Hall", nil), room(3, "Office", 1)]
    return PreviewModel(source: PreviewSource(title: "House", subtitle: "", sessions: [], rooms: rooms))
  }

  func testTheViewerOffersTheLevelsItsRoomsAreOn() {
    XCTAssertEqual(model().levels, [Level(0), Level(1)])
  }

  func testShowingALevelShowsOnlyTheRoomsOnIt() {
    let viewer = model()

    viewer.showLevel(Level(1))

    XCTAssertEqual(viewer.visibleRooms, ["0/1", "0/3"])
  }
}
