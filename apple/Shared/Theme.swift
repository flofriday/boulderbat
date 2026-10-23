import SwiftUI

extension Color {
    init(hex: UInt32) {
        self.init(.sRGB, red: Double((hex >> 16) & 255) / 255,
                  green: Double((hex >> 8) & 255) / 255, blue: Double(hex & 255) / 255, opacity: 1)
    }
}
extension Gym { var color: Color { Color(hex: hex) } }

enum BatStyle {
    static let yellow = Color(hex: 0xFFCC00)
    static let ink = Color(hex: 0x15191D)
    static func status(_ capacity: Double) -> Color {
        capacity < 40 ? Color(hex: 0x58D5A1) : capacity < 70 ? Color(hex: 0xEFC969) : Color(hex: 0xFF767B)
    }
}

struct Surface<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        content.padding(20)
            .background(.background, in: RoundedRectangle(cornerRadius: 24))
            .overlay(RoundedRectangle(cornerRadius: 24).stroke(.primary.opacity(0.07), lineWidth: 1))
    }
}

struct StatusPill: View {
    let value: Double
    var body: some View {
        Label(Occupancy.label(value), systemImage: value < 40 ? "leaf.fill" : "person.2.fill")
            .font(.caption.weight(.semibold)).foregroundStyle(BatStyle.status(value))
            .padding(.horizontal, 10).padding(.vertical, 5)
            .background(BatStyle.status(value).opacity(0.12), in: Capsule())
    }
}
