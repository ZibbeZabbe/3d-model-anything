import XCTest
import simd
@testable import HouseCapture

final class RoomJSONWallTests: XCTestCase {
  /// A wall in RoomPlan's CapturedRoom JSON shape, with values a Float cannot hold exactly.
  private let room = #"{"walls":[{"identifier":"W1","dimensions":[2.0517492,2.1642938,0],"transform":[-0.7317814,0,0.6815395,0,0,0.99999994,0,0,-0.6815394,0,-0.73178136,0,1.4212801,-0.18055037,1.7806723,0.99999994]}]}"#

  func testWallsParsedFromJSONSerializationDoublesKeepTheirSizeAndPosition() throws {
    let json = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(room.utf8)) as? [String: Any])

    let walls = RoomFootprint.Wall.parse(json)

    XCTAssertEqual(walls.count, 1)
    XCTAssertEqual(walls.first?.width ?? 0, 2.0517492, accuracy: 1e-5)
    XCTAssertEqual(walls.first?.height ?? 0, 2.1642938, accuracy: 1e-5)
    XCTAssertEqual(walls.first?.transform.columns.3.z ?? 0, 1.7806723, accuracy: 1e-5)
  }
}
