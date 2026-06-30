"""Segment CdA measurement: infer aerodynamic drag area from measured ride segments."""


def cda(segment, crr, weight, efficiency):
    """Claude_cda: solve a measured fitsegment for its effective CdA (clamped at 0)."""
    usedPower = segment.avg_power * efficiency
    usedPower -= segment.avg_speed * segment.grade * weight * 9.81 / 100
    usedPower -= weight * 9.81 * segment.avg_speed * crr
    usedPower /= segment.avg_speed ** 3
    usedPower /= 1.2
    usedPower *= 2
    return (max(usedPower, 0))


def rideCDA(segments, crr, weight, efficiency):
    """Claude_rideCDA: per-segment [cda, distance, grade] for segments faster than 2 m/s."""
    cdas = []
    for segment in segments:
        if segment.avg_speed > 2:
            cdas.append([cda(segment, crr, weight, efficiency), segment.distance, segment.grade])
    return (cdas)


def get_crr(watts):
    """Claude_get_crr: convert a measured rolling-resistance wattage to a Crr coefficient."""
    return (watts * 3.6 / (28.8 * 42.5 * 9.81))
