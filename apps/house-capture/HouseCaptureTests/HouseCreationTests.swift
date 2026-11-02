import XCTest
@testable import HouseCapture

@MainActor
final class HouseCreationTests: XCTestCase {
  private let instant = Date(timeIntervalSince1970: 1_800_000_000)
  private var created: [HouseProject] = []

  override func tearDownWithError() throws {
    for house in created { try? FileManager.default.removeItem(at: house.url) }
  }

  private func create(_ name: String) throws -> HouseProject {
    let house = try HouseProject.create(name: name, at: instant)
    created.append(house)
    return house
  }

  func testTwoHousesCreatedInTheSameSecondKeepTheirOwnFolders() throws {
    let first = try create("First")
    let second = try create("Second")

    XCTAssertNotEqual(first.id, second.id)
    XCTAssertEqual(try HouseProject.load(id: first.id).name, "First")
    XCTAssertEqual(try HouseProject.load(id: second.id).name, "Second")
  }
}
