import SwiftUI

/// Choices for a room's level, for a menu: every storey, plus clearing the level.
struct LevelChoices: View {
  let current: Level?
  let onPick: (Level?) -> Void

  var body: some View {
    ForEach(Level.choices.reversed(), id: \.self) { level in
      Button { onPick(level) } label: {
        if level == current { Label(level.name, systemImage: "checkmark") } else { Text(level.name) }
      }
    }
    if current != nil {
      Divider()
      Button("No level", role: .destructive) { onPick(nil) }
    }
  }
}
