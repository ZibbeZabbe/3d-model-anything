import XCTest
@testable import HouseCapture

final class DiagnosticsArchiveTests: XCTestCase {
  private var root: URL!
  private var session: URL!

  override func setUpWithError() throws {
    let base = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
    root = base.appendingPathComponent("Diagnostics", isDirectory: true)
    session = base.appendingPathComponent("sessions/2026-11-01 10.41.00", isDirectory: true)
    try FileManager.default.createDirectory(at: session, withIntermediateDirectories: true)
  }

  override func tearDownWithError() throws {
    try? FileManager.default.removeItem(at: root.deletingLastPathComponent())
  }

  private func archived() throws -> [String] {
    guard FileManager.default.fileExists(atPath: root.path) else { return [] }
    return try FileManager.default.contentsOfDirectory(atPath: root.path).sorted()
  }

  func testPreservesASessionsDiagnosticsUnderItsHouseAndSessionNames() throws {
    try Data(#"{"events":[]}"#.utf8).write(to: session.appendingPathComponent("diagnostics.json"))

    try DiagnosticsArchive(root: root).preserve(sessionFolder: session, house: "2026-11-01 10.40.00")

    XCTAssertEqual(try archived(), ["2026-11-01 10.40.00 2026-11-01 10.41.00.json"])
    let copy = try Data(contentsOf: root.appendingPathComponent("2026-11-01 10.40.00 2026-11-01 10.41.00.json"))
    XCTAssertEqual(String(decoding: copy, as: UTF8.self), #"{"events":[]}"#)
  }

  func testASessionWithoutDiagnosticsLeavesTheArchiveUntouched() throws {
    try DiagnosticsArchive(root: root).preserve(sessionFolder: session, house: "house")

    XCTAssertEqual(try archived(), [])
  }

  func testKeepsOnlyTheMostRecentArchives() throws {
    let archive = DiagnosticsArchive(root: root, capacity: 2)
    try Data("{}".utf8).write(to: session.appendingPathComponent("diagnostics.json"))
    // Modification dates order the archives: age each one before preserving the next.
    for (age, house) in [(300.0, "a"), (200.0, "b"), (100.0, "c")] {
      try archive.preserve(sessionFolder: session, house: house)
      let file = root.appendingPathComponent("\(house) \(session.lastPathComponent).json")
      try FileManager.default.setAttributes([.modificationDate: Date(timeIntervalSinceNow: -age)], ofItemAtPath: file.path)
    }

    XCTAssertEqual(try archived(), ["b 2026-11-01 10.41.00.json", "c 2026-11-01 10.41.00.json"])
  }
}
