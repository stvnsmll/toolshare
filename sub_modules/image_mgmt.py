
#imports
import os
import PIL
import qrcode
from flask import current_app as app
from PIL import Image



# Create local thumbnail
def save_local_thumbnail(image_uuid):
    UPLOAD_FOLDER = app.config['UPLOAD_FOLDER']

    file_thumb = UPLOAD_FOLDER + image_uuid + "_thumb.png"
    if os.path.exists(file_thumb):
        os.remove(file_thumb)
    MAX_SIZE = (75, 75)
    image = PIL.Image.open(UPLOAD_FOLDER + image_uuid + ".jpeg")
    image.thumbnail(MAX_SIZE, PIL.Image.ANTIALIAS)
    image.save(file_thumb)
    print("thumbnail created.")


# AWS S3 Storage functions
def delete_images_s3(image_uuid):
    s3 = app.config["s3_object"]

    key_name = image_uuid + ".jpeg"
    try:
        s3.delete_object(
            Bucket=app.config["S3_BUCKET"],
            Key=key_name
        )
    except Exception as e:
        print("Something Happened - FullFileDelete: ", e)
    key_name = image_uuid + "_thumb.png"
    try:
        s3.delete_object(
            Bucket=app.config["S3_BUCKET"],
            Key=key_name
        )
    except Exception as e:
        print("Something Happened - ThumbnailDelete: ", e)


def images_to_s3(image_uuid):
    s3 = app.config["s3_object"]
    UPLOAD_FOLDER = app.config['UPLOAD_FOLDER']

    # Upload image and thumbnail to AWS
    #delete images if they are stored on S3
    delete_images_s3(image_uuid)
    # upload to aws s3
    file_name = UPLOAD_FOLDER + image_uuid + ".jpeg"#full source filepath
    key_name = image_uuid + ".jpeg"#just the file name
    s3.upload_file(file_name, app.config["S3_BUCKET"], key_name, ExtraArgs={
        "ACL": "public-read",
        "ContentType": "image/jpeg"
    })

    file_name = UPLOAD_FOLDER + image_uuid + "_thumb.png"
    key_name = image_uuid + "_thumb.png"
    s3.upload_file(file_name, app.config["S3_BUCKET"], key_name, ExtraArgs={
        "ACL": "public-read",
        "ContentType": "image/png"
    })


def get_image_s3(image_uuid_with_ext, expire_in=3600):
    s3 = app.config["s3_object"]

    # just send the full asw filepath for now
    #return "{}{}".format(app.config["S3_LOCATION"], image_uuid_with_ext)  <--- delete this...
    # returns the presigned url for the full-sized image
    try:
        response = s3.generate_presigned_url('get_object',
                                                    Params={'Bucket': app.config["S3_BUCKET"],
                                                            'Key': image_uuid_with_ext},
                                                    ExpiresIn=expire_in)#seconds
    except:# ClientError as e:
        #logging.error(e)
        e = "get_image_s3, misc error"
        print("Something Happened - ImageFetchFail: ", e)
        return None

    # The response contains the presigned URL
    return response


def qr_code_image(url):
    #url is the full url of the address that needs to be put into the QR code
    qr_image = qrcode.make(url)
    type(qr_image)  # qrcode.image.PIL.PilImage
    #don't save the image, pass it back
    #img.save("static/toolimages/some_file.png")
    return qr_image


#QR CODE GENERATION
'''
#in the python script somewhere... (see in above function "qr_code_image")
img = qrcode.make("url...")
data = io.BytesIO()
img.save(data, "PNG")
encoded_qr_image = base64.b64encode(data.getvalue())

#pass to template:
qrcode_data=encoded_qr_image.decode('utf-8')

#in templage:
<img src="data:image/png;base64,{{ qrcode_data }}" alt="QR Code generation error" class="qrcode"><br>
'''
