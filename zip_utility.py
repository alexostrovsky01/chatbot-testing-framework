#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path
import zipfile

def zip_directory(dir_path: Path, output_path: Path):
    """
    Recursively zips a directory.

    Args:
        dir_path (Path): The path object of the directory to zip.
        output_path (Path): The path object for the output ZIP file.
    """
    if not dir_path.is_dir():
        raise NotADirectoryError(f"Error: The provided path '{dir_path}' is not a directory or does not exist.")

    print(f"Zipping directory '{dir_path}' to '{output_path}'...")

    try:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Using rglob('*') to iterate through all files and directories recursively
            for entry in dir_path.rglob('*'):
                # arcname is the path that the entry will have inside the zip archive
                arcname = entry.relative_to(dir_path)
                zipf.write(entry, arcname)
        
        print(f"\nSuccessfully created archive: {output_path}")

    except Exception as e:
        print(f"An error occurred during zipping: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    """Main function to parse arguments and initiate zipping."""
    parser = argparse.ArgumentParser(
        description="A command-line utility to recursively zip a directory.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument(
        "directory",
        type=str,
        help="The path to the directory to be zipped."
    )
    
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help=(
            "The full path for the output ZIP file.\n"
            "If not provided, the archive will be named after the directory\n"
            "(e.g., 'my_dir.zip') and placed in the same parent location."
        )
    )

    args = parser.parse_args()
    
    source_dir = Path(args.directory).resolve()
    
    if args.output:
        output_file = Path(args.output).resolve()
    else:
        # Default output path: parent directory + source directory name + .zip
        output_file = source_dir.parent / f"{source_dir.name}.zip"

    try:
        zip_directory(source_dir, output_file)
    except (NotADirectoryError, FileNotFoundError) as e:
        print(e, file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()