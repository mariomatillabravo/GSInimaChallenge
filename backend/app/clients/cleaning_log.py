"""Reporting what the cleaning rule dropped, shared by the AEMET client and the recorded source.

The parser only counts: it stays a pure function. Logging happens in the adapters, which know
the station and the month the records belong to.
"""

import logging

from app.clients.aemet_parser import ParsedObservations
from app.domain.stations import Station


def log_discarded(
    logger: logging.Logger, parsed: ParsedObservations, station: Station, month: str
) -> None:
    """Log how many records of one month the cleaning rule discarded, when it discarded any.

    INFO, not WARNING: a few unusable records are normal data quality, not a fault to act on.
    The counts are also ``extra`` fields, so JSON logs can be filtered and summed by them.
    """
    if parsed.discarded == 0:
        return
    logger.info(
        "Discarded %d of %d records for %s %s: no usable value or no valid timestamp.",
        parsed.discarded,
        parsed.received,
        station.id,
        month,
        extra={
            "station": station.id,
            "month": month,
            "records": parsed.received,
            "discarded": parsed.discarded,
        },
    )
