import XCTest
@testable import HouseCapture

final class PreviewSpanTests: XCTestCase {
  func testTheShownSpanRunsFromTheLowestFloorToTheHighestCeiling() {
    let span = PreviewScene.span(of: [(floor: 0, ceiling: 2.5), (floor: 2.8, ceiling: 5.3)])

    XCTAssertEqual(span.floor, 0)
    XCTAssertEqual(span.ceiling, 5.3)
  }

  func testWithNothingShownTheSpanIsAStandardStorey() {
    let span = PreviewScene.span(of: [])

    XCTAssertEqual(span.floor, 0)
    XCTAssertEqual(span.ceiling, 2.5)
  }
}
