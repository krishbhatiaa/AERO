"""Common Alerting Protocol (CAP-IN v1.2) XML exporter.

Converts internal alert dictionary structures into standard CAP-IN v1.2 XML format.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import Any

CAP_NAMESPACE = "urn:oasis:names:tc:emergency:cap:1.2"
SENDER_ID = "ewai-alert-engine@ncmrwf.gov.in"


def export_cap_xml(alert: dict[str, Any]) -> str:
    """Export an alert record to CAP-IN v1.2 XML string."""
    ET.register_namespace("", CAP_NAMESPACE)
    root = ET.Element(f"{{{CAP_NAMESPACE}}}alert")

    # Core CAP Alert Headers
    alert_id = alert.get("alert_id", alert.get("id", "ALERT-0001"))
    ET.SubElement(root, f"{{{CAP_NAMESPACE}}}identifier").text = str(alert_id)
    ET.SubElement(root, f"{{{CAP_NAMESPACE}}}sender").text = SENDER_ID
    
    sent_time = alert.get("created_at")
    if not sent_time:
        sent_time = datetime.now(UTC).isoformat()
    ET.SubElement(root, f"{{{CAP_NAMESPACE}}}sent").text = str(sent_time)
    
    ET.SubElement(root, f"{{{CAP_NAMESPACE}}}status").text = "Actual"
    ET.SubElement(root, f"{{{CAP_NAMESPACE}}}msgType").text = "Alert"
    ET.SubElement(root, f"{{{CAP_NAMESPACE}}}scope").text = "Public"

    # Info Block
    info = ET.SubElement(root, f"{{{CAP_NAMESPACE}}}info")
    ET.SubElement(info, f"{{{CAP_NAMESPACE}}}category").text = "Met"
    ET.SubElement(info, f"{{{CAP_NAMESPACE}}}event").text = str(alert.get("event_type", "Extreme Weather Anomaly"))

    severity = str(alert.get("severity", "MODERATE")).upper()
    cap_severity = "Severe" if severity == "SEVERE" else ("Moderate" if severity == "MODERATE" else "Minor")
    ET.SubElement(info, f"{{{CAP_NAMESPACE}}}severity").text = cap_severity
    
    ET.SubElement(info, f"{{{CAP_NAMESPACE}}}urgency").text = "Expected"
    ET.SubElement(info, f"{{{CAP_NAMESPACE}}}certainty").text = "Observed" if alert.get("confidence") == "HIGH" else "Likely"

    # Event codes (CAP-IN specific)
    event_code = ET.SubElement(info, f"{{{CAP_NAMESPACE}}}eventCode")
    ET.SubElement(event_code, f"{{{CAP_NAMESPACE}}}valueName").text = "SAME"
    ET.SubElement(event_code, f"{{{CAP_NAMESPACE}}}value").text = "SVR"

    headline = f"{severity} {alert.get('event_type', 'Weather Anomaly')} Alert - {alert.get('affected_area', 'India Region')}"
    ET.SubElement(info, f"{{{CAP_NAMESPACE}}}headline").text = headline

    desc = alert.get("rationale", alert.get("description", "Extreme weather anomaly detected by NCMRWF EWAI analytical system."))
    ET.SubElement(info, f"{{{CAP_NAMESPACE}}}description").text = str(desc)

    instruction = "Monitor local meteorological bulletins. Prepare emergency decision support measures if required."
    ET.SubElement(info, f"{{{CAP_NAMESPACE}}}instruction").text = instruction

    # Area Block
    area = ET.SubElement(info, f"{{{CAP_NAMESPACE}}}area")
    area_desc = alert.get("affected_area", "Bay of Bengal & Eastern India")
    ET.SubElement(area, f"{{{CAP_NAMESPACE}}}areaDesc").text = str(area_desc)

    lat = alert.get("centroid_lat", alert.get("lat", 20.0))
    lon = alert.get("centroid_lon", alert.get("lon", 86.0))
    # Standard CAP Circle representation: lat,lon radius_km
    ET.SubElement(area, f"{{{CAP_NAMESPACE}}}circle").text = f"{lat:.4f},{lon:.4f} 50.0"

    # Parameter metadata
    param_prob = ET.SubElement(info, f"{{{CAP_NAMESPACE}}}parameter")
    ET.SubElement(param_prob, f"{{{CAP_NAMESPACE}}}valueName").text = "Probability"
    ET.SubElement(param_prob, f"{{{CAP_NAMESPACE}}}value").text = f"{alert.get('probability', 0.85):.2f}"

    xml_str = ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")
    return xml_str


def export_cap_xml_feed(alerts: list[dict[str, Any]]) -> str:
    """Export a list of alerts as a composite CAP feed XML string."""
    ET.register_namespace("", CAP_NAMESPACE)
    feed = ET.Element(f"{{{CAP_NAMESPACE}}}capFeed")
    ET.SubElement(feed, f"{{{CAP_NAMESPACE}}}title").text = "NCMRWF Extreme Weather AI CAP Alert Feed"
    ET.SubElement(feed, f"{{{CAP_NAMESPACE}}}updated").text = datetime.now(UTC).isoformat()
    
    for alert in alerts:
        alert_xml_raw = export_cap_xml(alert)
        alert_elem = ET.fromstring(alert_xml_raw)
        feed.append(alert_elem)

    return ET.tostring(feed, encoding="utf-8", xml_declaration=True).decode("utf-8")
