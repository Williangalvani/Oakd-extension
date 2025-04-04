FROM luxonis/depthai-library

RUN apt update && apt install -y libgirepository1.0-dev gstreamer1.0-plugins-base libopenblas-dev gir1.2-gst-rtsp-server-1.0 python3-gi

RUN apt install -y ninja-build

COPY requirements.txt /requirements.txt
RUN pip install -r /requirements.txt && apt auto-remove -y ninja-build

COPY src /src
entrypoint python /src/stream.py

LABEL version="1.0.0"
LABEL permissions='\
{\
   "NetworkMode":"host",\
   "HostConfig":{\
      "Privileged":true,\
      "NetworkMode":"host",\
      "Binds":[\
         "/dev/bus/usb:/dev/bus/usb"\
      ],\
      "DeviceCgroupRules":[\
         "c 189:* rmw"\
      ]\
   }\
}'

LABEL authors='[\
    {\
        "name": "Willian Galvani",\
        "email": "willian@bluerobotics.com"\
    }\
]'
LABEL company='{\
        "about": "",\
        "name": "Blue Robotics",\
        "email": "support@bluerobotics.com"\
    }'
LABEL type="device-integration"
LABEL readme='https://raw.githubusercontent.com/Williangalvani/Oakd-extension/{tag}/Readme.md'
LABEL links='{\
        "website": "https://github.com/Williangalvani/Oakd-extension/",\
        "support": "https://github.com/Williangalvani/Oakd-extension/"\
    }'
LABEL requirements="core >= 1.1"