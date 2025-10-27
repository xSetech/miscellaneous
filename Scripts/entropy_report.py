#!/usr/bin/env python3
"""
File Entropy Analyzer
Measures and visualizes the entropy of a file across byte offsets.
"""

import sys
import math
from collections import Counter
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


def calculate_entropy(data):
    """Calculate Shannon entropy of a byte sequence."""
    if not data:
        return 0.0
    
    counts = Counter(data)
    total = len(data)
    entropy = 0.0
    
    for count in counts.values():
        probability = count / total
        entropy -= probability * math.log2(probability)
    
    return entropy


def analyze_file_entropy(filepath, window_size=256, step_size=128):
    """
    Analyze entropy across a file using a sliding window.
    
    Args:
        filepath: Path to the file to analyze
        window_size: Size of the sliding window in bytes
        step_size: Number of bytes to move the window each iteration
    
    Returns:
        tuple: (offsets, entropies, file_size)
    """
    offsets = []
    entropies = []
    
    with open(filepath, 'rb') as f:
        file_size = Path(filepath).stat().st_size
        
        position = 0
        while position < file_size:
            f.seek(position)
            data = f.read(window_size)
            
            if not data:
                break
            
            entropy = calculate_entropy(data)
            offsets.append(position)
            entropies.append(entropy)
            
            position += step_size
    
    return offsets, entropies, file_size


def find_significant_regions(offsets, entropies, file_size, threshold=1.0, min_span_bytes=8192):
    """
    Identify regions of significantly low entropy (runs of constant/repetitive data).
    High entropy regions are everything else.
    
    Args:
        threshold: Entropy threshold (below = low entropy, above = high entropy)
        min_span_bytes: Minimum span size in bytes to report (default 8KB)
    
    Returns:
        tuple: (low_entropy_regions, high_entropy_regions)
        Each region is a dict with 'start', 'end', 'avg_entropy'
    """
    low_regions = []
    high_regions = []
    
    current_low = None
    current_high = None
    
    for i, (offset, entropy) in enumerate(zip(offsets, entropies)):
        # Track low entropy regions (runs of constant/repetitive data)
        if entropy < threshold:
            if current_low is None:
                current_low = {'start': offset, 'entropies': [entropy]}
            else:
                current_low['entropies'].append(entropy)
            
            # Close high entropy region if one was open
            if current_high is not None:
                current_high['end'] = offset
                current_high['avg_entropy'] = sum(current_high['entropies']) / len(current_high['entropies'])
                span_size = current_high['end'] - current_high['start']
                # Calculate minimum span as percentage of file size or absolute minimum
                min_span = max(min_span_bytes, file_size * 0.005)  # 0.5% of file or min_span_bytes
                if span_size >= min_span:
                    high_regions.append(current_high)
                current_high = None
        else:
            if current_high is None:
                current_high = {'start': offset, 'entropies': [entropy]}
            else:
                current_high['entropies'].append(entropy)
            
            # Close low entropy region if one was open
            if current_low is not None:
                current_low['end'] = offset
                current_low['avg_entropy'] = sum(current_low['entropies']) / len(current_low['entropies'])
                span_size = current_low['end'] - current_low['start']
                # Calculate minimum span as percentage of file size or absolute minimum
                min_span = max(min_span_bytes, file_size * 0.005)  # 0.5% of file or min_span_bytes
                if span_size >= min_span:
                    low_regions.append(current_low)
                current_low = None
    
    # Close any open regions at end of file
    if current_low is not None:
        current_low['end'] = offsets[-1]
        current_low['avg_entropy'] = sum(current_low['entropies']) / len(current_low['entropies'])
        span_size = current_low['end'] - current_low['start']
        min_span = max(min_span_bytes, file_size * 0.005)
        if span_size >= min_span:
            low_regions.append(current_low)
    
    if current_high is not None:
        current_high['end'] = offsets[-1]
        current_high['avg_entropy'] = sum(current_high['entropies']) / len(current_high['entropies'])
        span_size = current_high['end'] - current_high['start']
        min_span = max(min_span_bytes, file_size * 0.005)
        if span_size >= min_span:
            high_regions.append(current_high)
    
    return low_regions, high_regions


def format_bytes(num_bytes):
    """Format byte count as human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if num_bytes < 1024.0:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} TB"


def plot_entropy(filepath, offsets, entropies, file_size, low_regions, high_regions, output_path):
    """Create and save the entropy visualization."""
    fig, ax = plt.subplots(figsize=(14, 8))
    
    # Plot main entropy curve
    ax.plot(offsets, entropies, linewidth=0.8, color='steelblue', alpha=0.8)
    
    # Function to create smart labels with width info
    def create_label(region, color_name):
        span_size = region['end'] - region['start']
        size_str = format_bytes(span_size)
        
        # Only show size for spans >= 4KB
        if span_size >= 4096:
            return f"0x{region['start']:X}\n[{size_str}]\n0x{region['end']:X}"
        else:
            return f"0x{region['start']:X}\n↓\n0x{region['end']:X}"
    
    # Function to determine if labels would overlap
    def calculate_label_positions(regions, base_y):
        """Calculate non-overlapping y positions for labels."""
        if not regions:
            return []
        
        # Sort regions by start position
        sorted_regions = sorted(regions, key=lambda r: r['start'])
        positions = []
        
        # Estimate label width as 10% of plot range
        plot_range = file_size
        min_spacing = plot_range * 0.08  # Minimum horizontal spacing
        
        current_row = 0
        last_end = -float('inf')
        
        for region in sorted_regions:
            region_center = (region['start'] + region['end']) / 2
            
            # Check if this region overlaps with previous in current row
            if region['start'] - last_end < min_spacing:
                current_row += 1
            else:
                current_row = 0
            
            # Calculate y position with vertical offset for each row
            y_pos = base_y + (current_row * 0.8)  # Stack labels vertically
            positions.append({'region': region, 'y': y_pos})
            last_end = region['end']
        
        return positions
    
    # Calculate positions for low entropy labels
    low_positions = calculate_label_positions(low_regions, 0.5)
    
    # Highlight low entropy regions
    for pos_info in low_positions:
        region = pos_info['region']
        y_pos = pos_info['y']
        
        ax.axvspan(region['start'], region['end'], alpha=0.2, color='green', label='_nolegend_')
        ax.axvline(region['start'], color='green', linestyle='--', linewidth=1, alpha=0.5)
        ax.axvline(region['end'], color='green', linestyle='--', linewidth=1, alpha=0.5)
        
        # Add text annotation with blue border for low entropy
        mid_point = (region['start'] + region['end']) / 2
        label_text = create_label(region, 'green')
        ax.text(mid_point, y_pos, label_text, 
                ha='center', va='center', fontsize=7, color='darkgreen',
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.8, edgecolor='blue', linewidth=1.5))
    
    # Calculate positions for high entropy labels
    high_positions = calculate_label_positions(high_regions, 7.5)
    
    # Highlight high entropy regions
    for pos_info in high_positions:
        region = pos_info['region']
        y_pos = pos_info['y']
        
        ax.axvspan(region['start'], region['end'], alpha=0.2, color='red', label='_nolegend_')
        ax.axvline(region['start'], color='red', linestyle='--', linewidth=1, alpha=0.5)
        ax.axvline(region['end'], color='red', linestyle='--', linewidth=1, alpha=0.5)
        
        # Add text annotation with red border for high entropy
        mid_point = (region['start'] + region['end']) / 2
        label_text = create_label(region, 'red')
        ax.text(mid_point, y_pos, label_text, 
                ha='center', va='center', fontsize=7, color='darkred',
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.8, edgecolor='red', linewidth=1.5))
    
    # Labels and title
    ax.set_xlabel('Byte Offset', fontsize=12, fontweight='bold')
    ax.set_ylabel('Shannon Entropy (bits)', fontsize=12, fontweight='bold')
    ax.set_title(f'File Entropy Analysis: {Path(filepath).name}', fontsize=14, fontweight='bold', pad=20)
    
    # Set y-axis limits for entropy (0-8 bits for byte entropy)
    ax.set_ylim(0, 8)
    ax.grid(True, alpha=0.3, linestyle=':', linewidth=0.5)
    
    # Format x-axis to show hexadecimal values
    def hex_formatter(x, pos):
        return f'0x{int(x):X}'
    
    from matplotlib.ticker import FuncFormatter
    ax.xaxis.set_major_formatter(FuncFormatter(hex_formatter))
    
    # Add statistics box
    avg_entropy = sum(entropies) / len(entropies)
    max_entropy = max(entropies)
    min_entropy = min(entropies)
    
    stats_text = (
        f"File Size: {format_bytes(file_size)} ({file_size:,} bytes)\n"
        f"Average Entropy: {avg_entropy:.3f} bits\n"
        f"Max Entropy: {max_entropy:.3f} bits\n"
        f"Min Entropy: {min_entropy:.3f} bits\n"
        f"Entropy Threshold: 1.0 bits\n"
        f"Low Entropy Regions: {len(low_regions)} (runs/padding)\n"
        f"High Entropy Regions: {len(high_regions)} (data/code)"
    )
    
    ax.text(0.98, 0.97, stats_text, transform=ax.transAxes,
            fontsize=9, verticalalignment='top', horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    # Legend
    low_patch = mpatches.Patch(color='green', alpha=0.3, label='Low Entropy (<1.0) - Runs/Padding')
    high_patch = mpatches.Patch(color='red', alpha=0.3, label='High Entropy (≥1.0) - Data/Code')
    ax.legend(handles=[low_patch, high_patch], loc='upper left', fontsize=9)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✓ Entropy graph saved to: {output_path}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python entropy_analyzer.py <filepath> [output_graph.png]")
        print("\nExample:")
        print("  python entropy_analyzer.py program.exe")
        print("  python entropy_analyzer.py data.bin entropy_plot.png")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else "entropy_graph.png"
    
    if not Path(input_file).exists():
        print(f"Error: File '{input_file}' not found.")
        sys.exit(1)
    
    print(f"Analyzing entropy of: {input_file}")
    print("This may take a moment for large files...\n")
    
    # Analyze the file
    offsets, entropies, file_size = analyze_file_entropy(input_file)
    
    # Find significant regions
    low_regions, high_regions = find_significant_regions(offsets, entropies, file_size)
    
    print(f"File size: {format_bytes(file_size)}")
    print(f"Average entropy: {sum(entropies)/len(entropies):.3f} bits")
    print(f"Found {len(low_regions)} low entropy regions")
    print(f"Found {len(high_regions)} high entropy regions\n")
    
    # Create visualization
    plot_entropy(input_file, offsets, entropies, file_size, low_regions, high_regions, output_file)
    
    print("\nDone!")


if __name__ == "__main__":
    main()
