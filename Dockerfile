FROM luxonis/depthai-library

RUN apt install -y libgirepository1.0-dev gstreamer1.0-plugins-bad gstreamer1.0-plugins-good gstreamer1.0-plugins-base libopenblas-dev gir1.2-gst-rtsp-server-1.0 python3-gi ninja-build

RUN git clone --depth 1 https://github.com/luxonis/depthai-experiments.git
# RUN python3 -m pip install -r depthai-experiments/gen2-rtsp-streaming/requirements.txt
RUN  pip install numpy
RUN  pip install PyGObject
COPY stream.py /stream.py
entrypoint /bin/bash
