import SwiftUI
import Charts

struct CapacityChart: View {
    let day: String
    let gyms: [Gym]
    let readings: [Reading]
    let forecasts: [LocationForecast]
    var compact = false
    var showsLastRecordedSample = false
    var now = Date.now
    @State private var selectedDate: Date?

    private var range: ClosedRange<Date> { Vienna.chartRange(day) }
    private var points: [(Gym, [GraphPoint])] {
        gyms.map { gym in
            (gym, GraphData.points(gym: gym.id, readings: readings,
                                  forecast: day == Vienna.day(now) ? forecasts.first { $0.locationId == gym.id } : nil,
                                  range: range))
        }
    }
    var body: some View {
        Chart {
            ForEach(points, id: \.0.id) { gym, values in
                ForEach(values) { point in
                    if let low = point.lower, let high = point.upper {
                        AreaMark(x: .value("Time", point.date), yStart: .value("Lower", low), yEnd: .value("Upper", high), series: .value("Range", "range-\(gym.id)"))
                            .foregroundStyle(gym.color.opacity(compact ? 0.13 : 0.12))
                            .interpolationMethod(.linear)
                    }
                    LineMark(x: .value("Time", point.date), y: .value("Occupancy", point.value), series: .value("Series", point.segment))
                        .foregroundStyle(gym.color)
                        .lineStyle(StrokeStyle(lineWidth: compact ? 2 : 2.5, dash: point.predicted ? [5, 4] : []))
                        .interpolationMethod(.linear)
                }
                if showsLastRecordedSample, let last = values.last(where: { !$0.predicted }) {
                    PointMark(x: .value("Time", last.date), y: .value("Occupancy", last.value))
                        .foregroundStyle(gym.color)
                        .symbolSize(compact ? 24 : 36)
                }
            }
            if day == Vienna.day(now), range.contains(now) {
                RuleMark(x: .value("Now", now)).foregroundStyle(Color.secondary.opacity(0.6))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 4]))
                    .annotation(position: .top, alignment: .leading) { if !compact { Text("Now").font(.caption2).foregroundStyle(Color.secondary) } }
            }
            if let selectedDate, !compact {
                RuleMark(x: .value("Selected", selectedDate)).foregroundStyle(Color.secondary.opacity(0.5))
                    .annotation(position: .top, alignment: .leading) {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(Vienna.time(selectedDate)).fontWeight(.semibold)
                            ForEach(points, id: \.0.id) { gym, values in
                                if let nearest = values.min(by: { abs($0.date.timeIntervalSince(selectedDate)) < abs($1.date.timeIntervalSince(selectedDate)) }), abs(nearest.date.timeIntervalSince(selectedDate)) < 900 {
                                    Text("\(gym.title)  \(nearest.value, specifier: "%.0f")%\(nearest.predicted ? " · predicted" : "")")
                                        .foregroundStyle(gym.color)
                                    if let lower = nearest.lower, let upper = nearest.upper {
                                        Text("80% range: \(lower, specifier: "%.0f")–\(upper, specifier: "%.0f")%")
                                            .foregroundStyle(.secondary)
                                    }
                                }
                            }
                        }.font(.caption).padding(10).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10))
                    }
            }
        }
        .chartXScale(domain: range)
        .chartYScale(domain: 0...100)
        .chartXAxis {
            AxisMarks(values: .stride(by: .hour, count: compact ? 6 : 4)) { axis in
                AxisGridLine().foregroundStyle(Color.secondary.opacity(0.10))
                AxisValueLabel(anchor: .top) { if let date = axis.as(Date.self) { Text(Vienna.time(date)).font(.system(size: compact ? 9 : 11)) } }
            }
        }
        .chartYAxis {
            if !compact {
                AxisMarks(position: .leading, values: [0, 25, 50, 75, 100]) { axis in
                    AxisGridLine(stroke: StrokeStyle(dash: [3, 4])).foregroundStyle(Color.secondary.opacity(0.13))
                    AxisValueLabel(anchor: .trailing) { if let value = axis.as(Int.self) { Text("\(value)%") } }
                }
            }
        }
        .chartLegend(.hidden)
        .chartXSelection(value: $selectedDate)
        .environment(\.timeZone, Vienna.zone)
        .accessibilityLabel("Occupancy chart for \(gyms.map(\.title).joined(separator: ", ")). Solid lines are recorded; dashed lines are predicted. Shading is the 80 percent prediction range.\(showsLastRecordedSample ? " The dot marks the last recorded sample." : "")")
    }
}

struct ChartLegend: View {
    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 16) { items }
            VStack(alignment: .leading, spacing: 8) { items }
        }.font(.caption).foregroundStyle(.secondary)
    }
    @ViewBuilder private var items: some View {
        Label { Text("Recorded") } icon: { Rectangle().frame(width: 20, height: 2) }
        Label { Text("Predicted") } icon: {
            Canvas { context, size in
                var path = Path(); path.move(to: CGPoint(x: 0, y: 1)); path.addLine(to: CGPoint(x: size.width, y: 1))
                context.stroke(path, with: .color(.secondary), style: StrokeStyle(lineWidth: 2, dash: [4, 3]))
            }.frame(width: 20, height: 2)
        }
        Label { Text("80% range") } icon: { RoundedRectangle(cornerRadius: 3).fill(.secondary.opacity(0.25)).frame(width: 20, height: 10) }
    }
}
