import XCTest
@testable import HouseCapture

/// The export contract (`apps/house-capture/schema/house-capture-5.schema.json`) is checked on
/// both sides through one reference export, `schema/fixture/`: this test proves the app writes
/// exactly that export; the Python suite proves it satisfies the schema and that the Mac
/// scripts read it. Changing an encoded field fails here until the fixture, the schema and the
/// readers are updated together.
final class ExportContractTests: XCTestCase {
  private let fixture = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("schema/fixture", isDirectory: true)
  private var output: URL!

  override func setUpWithError() throws {
    output = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
    for sub in ScanBundle.subfolders {
      try FileManager.default.createDirectory(at: output.appendingPathComponent(sub), withIntermediateDirectories: true)
    }
  }

  override func tearDownWithError() throws {
    try? FileManager.default.removeItem(at: output)
  }

  private static let identity: [Float] = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0.5, 1.5, -2, 1]
  private static let intrinsics: [Float] = [1500, 0, 0, 0, 1500, 0, 960, 720, 1]
  private static let captured = Date(timeIntervalSince1970: 1_793_530_000)

  private var manifest: Manifest {
    Manifest(
      createdAt: Self.captured, device: "iPhone17,1", systemVersion: "26.6.1",
      house: "2026-11-01 11.41.49", houseName: "Our house", session: "2026-11-01 11.43.17", zone: "area-1",
      alignment: .init(method: "first"), worldMap: "worldmap.arworldmap", worldMapStatus: "mapped",
      endedAt: Self.captured.addingTimeInterval(180),
      rooms: [RoomRecord(index: 0, name: "Bathroom", file: "rooms/room-0.json", usdz: "rooms/room-0.usdz",
                         capturedAt: Self.captured.addingTimeInterval(150), walls: 4, doors: 1, windows: 2,
                         openings: 0, objects: 5,
                         mesh: MeshRecord(file: "mesh/room-0.ply", anchors: 0, vertices: 3, faces: 1),
                         coverage: 0.5, photoCoverage: 50, detailSeconds: 140, detailPhotos: 1, data: nil)],
      structure: "structure.json", structureError: nil, mesh: nil, sceneReconstruction: nil,
      photos: "photos/photos.json", photoCount: 1, depthFrames: "depth/frames.json", depthFrameCount: 1,
      diagnostics: nil)
  }

  private var photos: [PhotoRecord] {
    [PhotoRecord(file: "photos/0000.jpg", room: 0, timestamp: 12.5, width: 1920, height: 1440,
                 transform: Self.identity, intrinsics: Self.intrinsics, tracking: "normal", manual: false,
                 exposure: 0.0125, blurPixels: 0.5, pass: "detail", highRes: false, camera: nil)]
  }

  private var depthFrames: [DepthRecorder.Record] {
    [DepthRecorder.Record(file: "depth/00000.f16z", confidence: "depth/00000.conf", rgb: "depth/00000.jpg",
                          rgbIntrinsics: [500, 0, 0, 0, 500, 0, 320, 240, 1], camera: nil, room: 0, timestamp: 12.5,
                          width: 256, height: 192, transform: Self.identity, intrinsics: [200, 0, 0, 0, 200, 0, 128, 96, 1])]
  }

  private func assertMatchesFixture(_ path: String, file: StaticString = #filePath, line: UInt = #line) throws {
    let written = try JSONSerialization.jsonObject(with: Data(contentsOf: output.appendingPathComponent(path))) as? NSObject
    let expected = try JSONSerialization.jsonObject(with: Data(contentsOf: fixture.appendingPathComponent(path))) as? NSObject
    XCTAssertEqual(written, expected, "\(path) differs from the reference export", file: file, line: line)
  }

  func testTheAppWritesTheReferenceExport() throws {
    let bundle = ScanBundle(url: output)
    try bundle.writeManifest(manifest)
    try bundle.savePhotos(photos)
    try bundle.writeJSON(depthFrames, to: "depth/frames.json")

    try assertMatchesFixture("manifest.json")
    try assertMatchesFixture("photos/photos.json")
    try assertMatchesFixture("depth/frames.json")
  }
}
