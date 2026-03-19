
import datetime

def find_timestamp(srt_path: str, keywords: list[str]) -> tuple[str, str] | None:
    """
    Parses an .srt file and searches for lines containing any of the keywords.
    Returns (start_time, end_time) with a 30-second buffer on each side,
    or None if no match is found.
    """
    def parse_time(time_str):
        h, m, s_ms = time_str.split(":")
        s, ms = s_ms.split(',')
        return datetime.timedelta(hours=int(h), minutes=int(m), seconds=int(s), milliseconds=int(ms))

    def format_time(td: datetime.timedelta) -> str:
        total_seconds = int(td.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02}"

    keywords_lower = [k.lower() for k in keywords]
    buffer = datetime.timedelta(seconds=30)

    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = content.strip().split("\n\n")

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue

        try:
            # Ignore the first line (subtitle number)
            time_str = lines[1]
            text_lines = lines[2:]
        except IndexError:
            continue

        start_time_str, end_time_str = time_str.split(" --> ")
        start_time = parse_time(start_time_str)
        end_time = parse_time(end_time_str)

        full_text = " ".join(text_lines).lower()

        for keyword in keywords_lower:
            if keyword in full_text:
                buffered_start = max(datetime.timedelta(0), start_time - buffer)
                buffered_end = end_time + buffer
                return format_time(buffered_start), format_time(buffered_end)

    return None
