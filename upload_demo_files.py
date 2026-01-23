#!/usr/bin/env python3
"""
Upload demo files to Cloudflare R2 storage
"""

import os
import sys
import boto3
from botocore.client import Config
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

def upload_demo_files():
    """Upload demo files to R2 storage"""

    # Load environment variables
    load_dotenv()

    # R2 configuration (you'll need to fill these in)
    account_id = os.getenv('CLOUDFLARE_R2_ACCOUNT_ID')
    access_key = os.getenv('CLOUDFLARE_R2_ACCESS_KEY_ID')
    secret_key = os.getenv('CLOUDFLARE_R2_SECRET_ACCESS_KEY')
    bucket_name = os.getenv('CLOUDFLARE_R2_BUCKET', 'runbot-media')

    if not all([account_id, access_key, secret_key]):
        print("❌ R2 credentials not found in environment variables")
        print("Please set: CLOUDFLARE_R2_ACCOUNT_ID, CLOUDFLARE_R2_ACCESS_KEY_ID, CLOUDFLARE_R2_SECRET_ACCESS_KEY")
        return False

    # Configure R2 client
    r2_client = boto3.client(
        's3',
        endpoint_url=f'https://{account_id}.r2.cloudflarestorage.com',
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version='s3v4')
    )

    # Test files to upload
    test_files_dir = Path(__file__).parent / 'test_files'
    demo_files = [
        'demo-text-001.txt',
        'demo-excel-001.csv',  # Note: CSV instead of XLSX for simplicity
        'demo-document-001.pdf',
        'demo-image-001.jpg',
        'demo-video-001.mp4',
        'demo-video-002.mp4'
    ]

    print("🚀 Uploading demo files to Cloudflare R2...")

    for filename in demo_files:
        file_path = test_files_dir / filename

        if not file_path.exists():
            print(f"⚠️  File not found: {filename}")
            continue

        try:
            # Upload file
            with open(file_path, 'rb') as file_data:
                r2_client.upload_fileobj(
                    file_data,
                    bucket_name,
                    filename,
                    ExtraArgs={
                        'ContentType': get_content_type(filename),
                        'ACL': 'public-read'  # Make files publicly accessible
                    }
                )

            print(f"✅ Uploaded: {filename}")

        except Exception as e:
            print(f"❌ Failed to upload {filename}: {e}")

    print("\n🎉 Demo files uploaded to R2!")
    print(f"Bucket: {bucket_name}")
    print("Files should now be visible in Cloudflare R2 dashboard")

    return True

def get_content_type(filename):
    """Get MIME content type based on file extension"""
    ext = filename.lower().split('.')[-1]

    content_types = {
        'txt': 'text/plain',
        'csv': 'text/csv',
        'pdf': 'application/pdf',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'mp4': 'video/mp4',
        'avi': 'video/x-msvideo',
        'mov': 'video/quicktime'
    }

    return content_types.get(ext, 'application/octet-stream')

if __name__ == "__main__":
    success = upload_demo_files()
    if success:
        print("\n📋 Next steps:")
        print("1. Check Cloudflare R2 dashboard to verify files are uploaded")
        print("2. Update demo data creation to use correct file URLs")
        print("3. Test file access through the web interface")
    else:
        print("\n❌ Upload failed. Check R2 credentials and try again.")