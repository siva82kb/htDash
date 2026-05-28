import subprocess
import json
from datetime import datetime
import pytz
from config import Config

class S3Operations:
    @staticmethod
    def upload_to_s3(local_path, s3_key):
        """Upload file to S3 bucket"""
        try:
            command = [
                "aws", "s3", "cp",
                local_path,
                f"s3://{Config.BUCKET_NAME}/{s3_key}"
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            return result.returncode == 0
        except Exception as e:
            print(f"S3 upload error: {e}")
            return False
    
    @staticmethod
    def get_last_modified(s3_key):
        """Get last modified time of S3 object"""
        try:
            command = [
                "aws", "s3api", "head-object",
                "--bucket", Config.BUCKET_NAME,
                "--key", s3_key,
                "--query", "LastModified",
                "--output", "text"
            ]
            
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode == 0:
                utc_time_str = result.stdout.strip()
                # Convert to IST
                utc_time = datetime.fromisoformat(utc_time_str.replace("Z", "+00:00"))
                ist_timezone = pytz.timezone("Asia/Kolkata")
                last_modified_ist = utc_time.astimezone(ist_timezone)
                return last_modified_ist.strftime("%Y-%m-%dT%H:%M:%S")
        except Exception as e:
            print(f"Error getting last modified: {e}")
        return None
    
    @staticmethod
    def get_last_modified_actilife(s3_prefix, use_hand):
        """Get last modified for Actilife data"""
        try:
            command = [
                "aws", "s3api", "list-objects-v2",
                "--bucket", Config.BUCKET_NAME,
                "--prefix", f"{s3_prefix}/{use_hand}",
                "--query", "sort_by(Contents,&LastModified)[-1].[Key,LastModified]",
                "--output", "json"
            ]
            
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode == 0:
                output = result.stdout.strip()
                if output and output != "null":
                    key_lastmodified = json.loads(output)
                    if key_lastmodified:
                        s3_key, last_modified_utc = key_lastmodified
                        # Convert to IST
                        utc_time = datetime.fromisoformat(last_modified_utc.replace("Z", "+00:00"))
                        ist_timezone = pytz.timezone("Asia/Kolkata")
                        last_modified_ist = utc_time.astimezone(ist_timezone)
                        return last_modified_ist.strftime("%Y-%m-%dT%H:%M:%S")
        except Exception as e:
            print(f"Error getting Actilife last modified: {e}")
        return None