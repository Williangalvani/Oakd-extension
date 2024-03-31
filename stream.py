#!/usr/bin/env python3

import depthai as dai
import gi
import threading

gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib
import queue

class RtspSystem(GstRtspServer.RTSPMediaFactory):
  def __init__(self, **properties):
    super(RtspSystem, self).__init__(**properties)
    self.data_queue = queue.Queue()
    self.appsrc = None
    # Configure the launch string for H.264
    self.launch_string = 'appsrc name=source is-live=true block=true format=GST_FORMAT_TIME ! video/x-h264,stream-format=byte-stream,alignment=au ! rtph264pay name=pay0 config-interval=1 pt=96'

  def send_data(self, data):
      if self.appsrc:
        retval = self.appsrc.emit('push-buffer', Gst.Buffer.new_wrapped(data))
        if retval != Gst.FlowReturn.OK:
          print(f"Error pushing buffer to RTSP pipeline: {retval}")
    #self.data_queue.put(data)

  def start(self):
    t = threading.Thread(target=self._thread_rtsp)
    t.start()

  def _thread_rtsp(self):
    loop = GLib.MainLoop()
    loop.run()

  def on_need_data(self, src, length):
    if not self.data_queue.empty():
      data = self.data_queue.get()
      retval = src.emit('push-buffer', Gst.Buffer.new_wrapped(data))
      if retval != Gst.FlowReturn.OK:
        print(f"Error pushing buffer to RTSP pipeline: {retval}")

  def do_create_element(self, url):
    return Gst.parse_launch(self.launch_string)

  def do_configure(self, rtsp_media):
    self.appsrc = rtsp_media.get_element().get_child_by_name('source')
    self.appsrc.connect('need-data', self.on_need_data)
        
class RTSPServer(GstRtspServer.RTSPServer):
    def __init__(self, **properties):
        super(RTSPServer, self).__init__(**properties)
        self.rtsp = RtspSystem()
        self.rtsp.set_shared(True)
        self.get_mount_points().add_factory("/preview", self.rtsp)
        self.attach(None)
        Gst.init(None)
        self.rtsp.start()

    def send_data(self, data):
        self.rtsp.send_data(data)

# Create pipeline
pipeline = dai.Pipeline()

# Create left/right mono cameras for Stereo depth
monoLeft = pipeline.create(dai.node.MonoCamera)
monoLeft.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
monoLeft.setCamera("left")

monoRight = pipeline.create(dai.node.MonoCamera)
monoRight.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
monoRight.setCamera("right")

# Create a node that will produce the depth map
depth = pipeline.create(dai.node.StereoDepth)
depth.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.HIGH_DENSITY)
depth.initialConfig.setMedianFilter(dai.MedianFilter.KERNEL_7x7)
depth.setLeftRightCheck(False)
depth.setExtendedDisparity(False)
# Subpixel disparity is of UINT16 format, which is unsupported by VideoEncoder
depth.setSubpixel(False)
monoLeft.out.link(depth.left)
monoRight.out.link(depth.right)

# Colormap
colormap = pipeline.create(dai.node.ImageManip)
colormap.initialConfig.setColormap(dai.Colormap.TURBO, depth.initialConfig.getMaxDisparity())
colormap.initialConfig.setFrameType(dai.ImgFrame.Type.NV12)

videoEnc = pipeline.create(dai.node.VideoEncoder)
# Depth resolution/FPS will be the same as mono resolution/FPS
videoEnc.setDefaultProfilePreset(monoLeft.getFps(), dai.VideoEncoderProperties.Profile.H264_HIGH)

# Link
depth.disparity.link(colormap.inputImage)
colormap.out.link(videoEnc.input)

xout = pipeline.create(dai.node.XLinkOut)
xout.setStreamName("enc")
videoEnc.bitstream.link(xout.input)
# Start the RTSP server
server = RTSPServer()

# Connect to device and start pipeline
with dai.Device(pipeline) as device:

    # Output queue will be used to get the encoded data from the output defined above
    q = device.getOutputQueue(name="enc", maxSize=30, blocking=True)

    print("RTSP stream available at rtsp://<server-ip>:8554/preview")
    print("Press Ctrl+C to stop encoding...")

    try:
        while True:
            encData = q.get().getData()
            server.send_data(encData)
    except KeyboardInterrupt:
        # Keyboard interrupt (Ctrl + C) detected
        pass