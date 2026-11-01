import Foundation

/// Keeps the diagnostics of deleted or abandoned sessions outside the house folders, so the
/// evidence of a failed capture survives the session it describes (Documents/Diagnostics/).
/// Bounded: only the most recent `capacity` archives are kept.
struct DiagnosticsArchive {
  let root: URL
  var capacity = 20

  static let fileName = "diagnostics.json"

  /// The app's archive, beside the Houses folder.
  static var standard: DiagnosticsArchive {
    DiagnosticsArchive(root: HouseProject.root.deletingLastPathComponent().appendingPathComponent("Diagnostics", isDirectory: true))
  }

  /// Copies a session's diagnostics.json, if it has one, to "<house> <session>.json".
  ///
  /// # Errors
  /// Throws when the archive folder cannot be created or the copy fails.
  func preserve(sessionFolder: URL, house: String) throws {
    let fm = FileManager.default
    let source = sessionFolder.appendingPathComponent(Self.fileName)
    guard fm.fileExists(atPath: source.path) else { return }
    try fm.createDirectory(at: root, withIntermediateDirectories: true)
    let target = root.appendingPathComponent("\(house) \(sessionFolder.lastPathComponent).json")
    if fm.fileExists(atPath: target.path) { try fm.removeItem(at: target) }
    try fm.copyItem(at: source, to: target)
    try prune()
  }

  private func prune() throws {
    let fm = FileManager.default
    let files = try fm.contentsOfDirectory(at: root, includingPropertiesForKeys: [.contentModificationDateKey])
    let newestFirst = files.sorted { modified($0) > modified($1) }
    for stale in newestFirst.dropFirst(capacity) { try fm.removeItem(at: stale) }
  }

  private func modified(_ url: URL) -> Date {
    (try? url.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
  }
}
