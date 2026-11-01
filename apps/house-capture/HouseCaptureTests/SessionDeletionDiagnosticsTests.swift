import XCTest
@testable import HouseCapture

/// Deleting or abandoning a session, or a whole house, must keep the evidence of what happened.
@MainActor
final class SessionDeletionDiagnosticsTests: XCTestCase {
  private var house: HouseProject!
  private let sessionID = "2026-11-01 10.41.00"

  override func setUpWithError() throws {
    house = try HouseProject.create(name: "Diagnostics test \(UUID())")
    house.beginSession(id: sessionID, zone: "area-1", alignment: .init(method: "first"))
    try house.save()
    let folder = house.url.appendingPathComponent("sessions/\(sessionID)", isDirectory: true)
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    try Data(#"{"events":[{"t":3,"what":"tracking limited:relocalizing"}]}"#.utf8).write(to: folder.appendingPathComponent("diagnostics.json"))
  }

  override func tearDownWithError() throws {
    try? FileManager.default.removeItem(at: house.url)
    try? FileManager.default.removeItem(at: archived)
  }

  private var archived: URL {
    DiagnosticsArchive.standard.root.appendingPathComponent("\(house.id) \(sessionID).json")
  }

  func testDeletingASessionKeepsItsDiagnostics() throws {
    try HouseProject.deleteSession(houseID: house.id, sessionID: sessionID)

    XCTAssertTrue(FileManager.default.fileExists(atPath: archived.path))
  }

  func testDeletingAHouseKeepsTheDiagnosticsOfItsSessions() throws {
    try house.delete()

    XCTAssertTrue(FileManager.default.fileExists(atPath: archived.path))
  }
}
