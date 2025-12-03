#!/usr/bin/env python3
"""
macOS Log Filter
"""

import re
import argparse
import sys
import signal
from datetime import datetime
from typing import List, Tuple, Optional

# Handle broken pipe errors gracefully (e.g., when piping to head)
# SIGPIPE is not available on Windows
if hasattr(signal, 'SIGPIPE'):
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)


class LogEntry:
    """Represents a single log entry, potentially with multiple lines."""

    def __init__(self, main_line: str, continuation_lines: List[str] = None):
        self.main_line = main_line
        self.continuation_lines = continuation_lines or []
        self._parse_main_line()

    def _parse_main_line(self):
        """Parse the main log line to extract timestamp and process name."""
        # Timestamp pattern: 2025-12-03 15:23:25.803042-0800
        timestamp_pattern = r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+[+-]\d{4})'

        match = re.match(timestamp_pattern, self.main_line)
        if match:
            timestamp_str = match.group(1)
            # Parse the timestamp
            # Format: YYYY-MM-DD HH:MM:SS.ffffff-HHMM
            try:
                self.timestamp = datetime.strptime(timestamp_str[:-5], '%Y-%m-%d %H:%M:%S.%f')
            except ValueError:
                self.timestamp = None
        else:
            self.timestamp = None

        # Extract process name (comes before the first colon after the TTL field)
        # Split on whitespace and find the field before the first colon
        # Format: timestamp thread type activity pid ttl process_name: ...
        parts = self.main_line.split(None, 7)  # Split on whitespace, max 8 parts
        if len(parts) >= 8:
            # The 8th part contains "process_name: rest of line"
            remainder = parts[7]
            colon_pos = remainder.find(':')
            if colon_pos > 0:
                self.process_name = remainder[:colon_pos].strip()
            else:
                self.process_name = None
        else:
            self.process_name = None

    def matches_filter(self, start_time: Optional[datetime] = None,
                       end_time: Optional[datetime] = None,
                       processes: Optional[List[str]] = None) -> bool:
        """Check if this log entry matches the filter criteria (to be REMOVED)."""
        # Check timestamp range
        if self.timestamp:
            if start_time and self.timestamp < start_time:
                return False
            if end_time and self.timestamp > end_time:
                return False

        # Check process name
        if processes and self.process_name:
            if self.process_name not in processes:
                return False

        return True

    def to_string(self) -> str:
        """Convert the log entry back to string format."""
        lines = [self.main_line]
        lines.extend(self.continuation_lines)
        return '\n'.join(lines)


def is_main_log_line(line: str) -> bool:
    """Check if a line is a main log line (starts with timestamp)."""
    timestamp_pattern = r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+[+-]\d{4}'
    return bool(re.match(timestamp_pattern, line))


def parse_log_file(file_path: str, quiet: bool = True) -> List[LogEntry]:
    """Parse a log file into LogEntry objects."""
    entries = []
    current_entry = None

    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.rstrip('\n')

            if is_main_log_line(line):
                # Save previous entry if exists
                if current_entry:
                    entries.append(current_entry)

                # Start new entry
                current_entry = LogEntry(line)
            else:
                # Continuation line
                if current_entry:
                    current_entry.continuation_lines.append(line)
                # If no current entry, skip orphaned continuation line

        # Don't forget the last entry
        if current_entry:
            entries.append(current_entry)

    return entries


def filter_entries(entries: List[LogEntry],
                   start_time: Optional[datetime] = None,
                   end_time: Optional[datetime] = None,
                   processes: Optional[List[str]] = None) -> List[LogEntry]:
    """Filter log entries - REMOVES entries that match the criteria."""
    return [entry for entry in entries if not entry.matches_filter(start_time, end_time, processes)]


def parse_datetime(date_str: str) -> datetime:
    """Parse a datetime string in various formats."""
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d',
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    raise ValueError(f"Unable to parse datetime: {date_str}")


def main():
    parser = argparse.ArgumentParser(
        description='Parse and filter macOS log files (removes matching lines)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Remove iTerm2 logs
  %(prog)s logs.txt --process iTerm2

  # Remove logs before a time
  %(prog)s logs.txt --before "2025-12-03 15:23:26"

  # Remove logs after a time
  %(prog)s logs.txt --after "2025-12-03 15:23:26"

  # Remove multiple processes
  %(prog)s logs.txt --process iTerm2 --process WindowServer
        '''
    )

    parser.add_argument('input_file', help='Input log file to parse')
    parser.add_argument('--after', '--start', dest='start_time',
                        help='Remove logs after this time (YYYY-MM-DD HH:MM:SS)')
    parser.add_argument('--before', '--end', dest='end_time',
                        help='Remove logs before this time (YYYY-MM-DD HH:MM:SS)')
    parser.add_argument('--process', '-p', action='append', dest='processes',
                        help='Remove logs from this process (can be specified multiple times)')
    parser.add_argument('--output', '-o', dest='output_file',
                        help='Output file (default: stdout)')
    parser.add_argument('--stats', action='store_true',
                        help='Show statistics about the log entries')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show informational messages (default: quiet)')

    args = parser.parse_args()

    # Quiet by default, verbose if requested
    quiet = not args.verbose

    # Parse time arguments
    start_time = None
    end_time = None

    if args.start_time:
        try:
            start_time = parse_datetime(args.start_time)
        except ValueError as e:
            parser.error(f"Invalid start time: {e}")

    if args.end_time:
        try:
            end_time = parse_datetime(args.end_time)
        except ValueError as e:
            parser.error(f"Invalid end time: {e}")

    # Parse log file
    if not quiet:
        print(f"Parsing log file: {args.input_file}", file=sys.stderr)
    entries = parse_log_file(args.input_file, quiet=quiet)
    if not quiet:
        print(f"Found {len(entries)} log entries", file=sys.stderr)

    # Apply filters (removes matching entries)
    filtered_entries = filter_entries(entries, start_time, end_time, args.processes)
    if not quiet:
        print(f"After filtering: {len(filtered_entries)} entries remaining", file=sys.stderr)
        print(f"Removed: {len(entries) - len(filtered_entries)} entries", file=sys.stderr)

    # Show statistics if requested
    if args.stats:
        print("\n=== Statistics ===", file=sys.stderr)
        print(f"Total entries: {len(entries)}", file=sys.stderr)
        print(f"Removed entries: {len(entries) - len(filtered_entries)}", file=sys.stderr)
        print(f"Remaining entries: {len(filtered_entries)}", file=sys.stderr)

        # Count removed by process
        removed_entries = [e for e in entries if e not in filtered_entries]
        process_counts = {}
        for entry in removed_entries:
            if entry.process_name:
                process_counts[entry.process_name] = process_counts.get(entry.process_name, 0) + 1

        if process_counts:
            print("\nRemoved entries by process:", file=sys.stderr)
            for process, count in sorted(process_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"  {process}: {count}", file=sys.stderr)
        print(file=sys.stderr)

    # Output results
    try:
        if args.output_file:
            with open(args.output_file, 'w', encoding='utf-8') as f:
                for entry in filtered_entries:
                    f.write(entry.to_string() + '\n')
            if not quiet:
                print(f"Output written to: {args.output_file}", file=sys.stderr)
        else:
            for entry in filtered_entries:
                print(entry.to_string())
    except BrokenPipeError:
        # Python flushes standard streams on exit; redirect remaining output
        # to devnull to avoid another BrokenPipeError at shutdown
        devnull = open('/dev/null', 'w')
        sys.stdout = devnull
        sys.exit(0)


if __name__ == '__main__':
    main()
