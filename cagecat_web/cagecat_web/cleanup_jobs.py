import os
import shutil
import time
from datetime import datetime, timedelta


def delete_old_directories(target_dir, excluded_dir, age_limit):
    """Remove directories older than n days.

    Arguments:
        target_dir: the target directory in which dirs should be removed
        excluded_dir: the excluded example directory
        age_limit: the age limit of directories in days
    """
    now = datetime.now()
    age_limit_delta = timedelta(days=age_limit)

    for dirname in os.listdir(target_dir):
        dirpath = os.path.join(target_dir, dirname)
        if os.path.isdir(dirpath) and dirname != excluded_dir:
            dir_mod_time = datetime.fromtimestamp(os.path.getmtime(dirpath))
            if now - dir_mod_time > age_limit_delta:
                shutil.rmtree(dirpath, ignore_errors=True)


def main():
    """Runs an infinite loop and executes cleanup every 24 hours."""
    base_dir = os.path.dirname(os.path.abspath(__file__))  # Path to /cagecat_web/cagecat_web/
    upload_path = os.path.join(base_dir, "upload")

    # Make sure upload directory exists
    os.makedirs(upload_path, exist_ok=True)

    while True:
        delete_old_directories(upload_path, "example", 30)
        time.sleep(86400)  # Sleep for 24 hours


if __name__ == "__main__":
    main()