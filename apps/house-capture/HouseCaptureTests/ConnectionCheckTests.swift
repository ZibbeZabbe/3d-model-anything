import XCTest
import simd
@testable import HouseCapture

final class ConnectionCheckTests: XCTestCase {
  private func square(x: Float, z: Float, size: Float, floorY: Float = 0) -> RoomFootprint {
    RoomFootprint(outline: [SIMD2(x, z), SIMD2(x + size, z), SIMD2(x + size, z + size), SIMD2(x, z + size)], floorY: floorY)
  }

  func testRoomsSideBySideOnTheSameFloorPass() {
    let check = ConnectionCheck(placed: square(x: 0, z: 0, size: 2), reference: square(x: 2.1, z: 0, size: 2))

    XCTAssertEqual(check.overlap, 0, accuracy: 0.01)
    XCTAssertEqual(check.issues, [])
  }

  func testARoomPlacedOnTopOfTheReferenceIsFlagged() {
    let check = ConnectionCheck(placed: square(x: 0, z: 0, size: 2), reference: square(x: 1, z: 0, size: 2))

    XCTAssertEqual(check.overlap, 0.5, accuracy: 0.05)
    XCTAssertEqual(check.issues, [.overlap])
  }

  func testAFloorStepBetweenTheRoomsIsFlagged() {
    let check = ConnectionCheck(placed: square(x: 0, z: 0, size: 2, floorY: 0.12), reference: square(x: 2.1, z: 0, size: 2))

    XCTAssertEqual(check.floorStep, 0.12, accuracy: 0.001)
    XCTAssertEqual(check.issues, [.floorStep])
  }

  func testTheFootprintTakesTheFloorAndOutlineFromWallsUnderThePlacement() {
    // One 2 m wide, 2.4 m high wall centred at (0, 1.2, 0) in session space, running along x.
    let wall = RoomFootprint.Wall(transform: simd_float4x4(translation: SIMD3(0, 1.2, 0)), width: 2, height: 2.4)
    let lift = simd_float4x4(translation: SIMD3(5, 0.3, 0))

    let footprint = RoomFootprint(walls: [wall], placement: lift)

    XCTAssertEqual(footprint.floorY, 0.3, accuracy: 0.001)
    XCTAssertEqual(Set(footprint.outline.map { [$0.x, $0.y] }), [[4, 0], [6, 0]])
  }
}

private extension simd_float4x4 {
  init(translation t: SIMD3<Float>) {
    self = matrix_identity_float4x4
    columns.3 = SIMD4(t, 1)
  }
}
