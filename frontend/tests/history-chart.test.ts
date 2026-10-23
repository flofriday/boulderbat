import assert from "node:assert/strict"
import test from "node:test"
import { chartData, dayRange, shiftDate, validDay, viennaDay } from "../src/lib/history-chart.ts"
import type { PredictionResponse } from "../src/lib/history-chart.ts"

test("Vienna day and range remain correct across UTC offsets and DST", () => {
  assert.equal(viennaDay(new Date("2026-10-23T22:30:00Z")), "2026-10-24")
  for (const [day, start, end] of [
    ["2026-03-28", "2026-03-28T07:00:00.000Z", "2026-03-28T23:00:00.000Z"],
    ["2026-03-29", "2026-03-29T06:00:00.000Z", "2026-03-29T22:00:00.000Z"],
    ["2026-10-24", "2026-10-24T06:00:00.000Z", "2026-10-24T22:00:00.000Z"],
    ["2026-10-25", "2026-10-25T07:00:00.000Z", "2026-10-25T23:00:00.000Z"],
  ]) {
    assert.equal(dayRange(day).start.toISOString(), start)
    assert.equal(dayRange(day).end.toISOString(), end)
  }
  assert.equal(shiftDate("2026-12-31", 1), "2027-01-01")
  assert.equal(validDay("2026-02-30"), false)
  assert.equal(validDay("2026-10-23"), true)
})

test("prediction points cannot connect observed data across gaps", () => {
  const prediction: PredictionResponse = {
    date: "2026-10-23", generated_at: "2026-10-23T12:35:00Z", context_end: "2026-10-23T12:30:00Z",
    valid_until: "2026-10-23T21:59:59Z", locations: [{ location_id: 262, title: "Gym", status: "ok", reason: null,
      points: [{ recorded_at: "2026-10-23T12:35:00Z", capacity: 30, p10: 20, p90: 40 },
               { recorded_at: "2026-10-23T12:45:00Z", capacity: 35, p10: 25, p90: 45 }] }],
  }
  const readings = [
    { location_id: 262, title: "Gym", capacity: 20, recorded_at: "2026-10-23T12:00:00Z" },
    { location_id: 262, title: "Gym", capacity: 25, recorded_at: "2026-10-23T12:30:00Z" },
  ]
  const data = chartData(readings, prediction, new Set(["262"]))
  assert.equal(data.observed.length, 3)
  assert.equal(data.observed[1].observed_262, null)
  assert.equal(data.future.length, 2)
  assert.deepEqual(data.future[0].uncertainty_262, [20, 40])
  assert.deepEqual(data.future[1].uncertainty_262, [25, 45])
  assert.ok(data.future.every(point => !("observed_262" in point)))
  assert.ok(data.observed.every(point => !("uncertainty_262" in point)))
  assert.equal(data.lastReading, Date.parse("2026-10-23T12:30:00Z"))
  assert.deepEqual(data.connectors, [{ location_id: 262, data: [
    { ts: Date.parse("2026-10-23T12:30:00Z"), capacity: 25 },
    { ts: Date.parse("2026-10-23T12:35:00Z"), capacity: 30 },
  ] }])
  assert.equal(chartData(readings, undefined, new Set(["262"])).future.length, 0)
  assert.equal(chartData(readings, prediction, new Set(["260"])).data.length, 0)
})

test("connect each gym to its own latest reading, regardless of input order", () => {
  const prediction: PredictionResponse = {
    date: "2026-10-23", generated_at: "2026-10-23T12:35:00Z", context_end: "2026-10-23T12:30:00Z",
    valid_until: "2026-10-23T21:59:59Z", locations: [262, 263].map(id => ({
      location_id: id, title: "Gym", status: "ok", reason: null,
      points: [{ recorded_at: "2026-10-23T12:35:00Z", capacity: 30, p10: 20, p90: 40 }],
    })),
  }
  const readings = [
    { location_id: 262, title: "A", recorded_at: "2026-10-23T12:31:00Z", capacity: 26 },
    { location_id: 263, title: "B", recorded_at: "2026-10-23T12:30:00Z", capacity: 27 },
    { location_id: 262, title: "A", recorded_at: "2026-10-23T12:25:00Z", capacity: 1 },
  ]
  const data = chartData(readings, prediction, new Set(["262", "263"]))
  assert.equal(data.lastReading, Date.parse(readings[0].recorded_at))
  assert.deepEqual(data.connectors.map(c => c.data[0].capacity), [26, 27])
  assert.deepEqual(data.future[0].uncertainty_262, [20, 40])
  const historical = chartData(readings, undefined, new Set(["262", "263"]))
  assert.equal(historical.lastReading, null)
  assert.deepEqual(historical.connectors, [])

  const stale = chartData([readings[2]], prediction, new Set(["262"]))
  assert.equal(stale.connectors.length, 1)
  const outage = chartData([{ ...readings[2], recorded_at: "2026-10-23T12:00:00Z" }], prediction, new Set(["262"]))
  assert.deepEqual(outage.connectors, [])
  const noReadings = chartData([], prediction, new Set(["262"]))
  assert.equal(noReadings.lastReading, null)
  assert.deepEqual(noReadings.connectors, [])
  assert.equal(noReadings.future.length, 1)
})
