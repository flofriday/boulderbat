import Foundation

// Compile with Shared/*.swift and Widgets/*.swift, defining WIDGET_PREVIEW to
// exclude the widget bundle entry point. Reads the public API; changes no widgets.
@main
struct VerifyWidgetSelection {
    static func main() async throws {
        let expected = [262, 263, 264, 265, 1001, 284, 260, 261]
        for (choice, id) in zip(GymChoice.allCases, expected) {
            let intent = GymWidgetIntent()
            intent.location = choice.gym.title
            precondition(intent.selectedGym.id == id)
            intent.location = choice.rawValue
            precondition(intent.selectedGym.id == id)
        }
        let intent = GymWidgetIntent()
        for choice in [GymChoice.hannovergasse, .stpoelten, .seestadt] {
            intent.location = choice.gym.title
            let entry = await CapacityProvider().load(intent)
            precondition(entry.gym.id == choice.gym.id)
            precondition(entry.snapshot?.location(choice.gym.id)?.id == choice.gym.id)
            precondition(entry.snapshot?.readings.allSatisfy { $0.locationId == choice.gym.id } == true)
            print("Verified \(entry.gym.title): live + history match \(entry.gym.id)")
        }
    }
}
