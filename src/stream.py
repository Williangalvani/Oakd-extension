#!/usr/bin/env python3

import depthai as dai
import gi
import threading
from register_stream import check_streams

gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib, GstRtsp
import queue
import os

socket_rgb_path = "/tmp/socketrgb"
socket_depth_path = "/tmp/socketdepth"

receive_pipeline = "shmsrc is-live=true socket-path={} do-timestamp=true ! application/x-rtp,media=video,clock-rate=90000,encoding-name=H264 ! rtph264depay ! h264parse config-interval=1 ! queue leaky=upstream ! rtph264pay name=pay0 pt=96"
app_pipeline = "appsrc name=source do-timestamp=true is-live=true format=time ! h264parse ! queue leaky=downstream ! rtph264pay config-interval=1 pt=96 ! shmsink wait-for-connection=false sync=true socket-path={}"

class RtspSystem(GstRtspServer.RTSPMediaFactory):
  def __init__(self, **properties):
    super(RtspSystem, self).__init__(**properties)

  def start(self):
    t = threading.Thread(target=self._thread_rtsp)
    t.start()

  def _thread_rtsp(self):
    loop = GLib.MainLoop()
    loop.run()

  def on_need_data(self, src, length):
    print(f"need data {length}")


  def on_no_need_data(self, src):
    print("no need data")


  def do_create_element(self, url):
    name = url.abspath.split('/')[-1]
    if name == 'rgb':
      return Gst.parse_launch(receive_pipeline.format(socket_rgb_path))
    return Gst.parse_launch(receive_pipeline.format(socket_depth_path))

  def do_configure(self, rtsp_media):
    self.appsrc = rtsp_media.get_element().get_child_by_name('source')
    self.set_profiles(GstRtsp.RTSPProfile.AVPF)
    #self.appsrc.connect('need-data', self.on_need_data)
    #self.appsrc.connect('enough-data', self.on_no_need_data)

class RTSPServer(GstRtspServer.RTSPServer):
    def __init__(self, **properties):
        super(RTSPServer, self).__init__(**properties)
        self.rgb_rtsp = RtspSystem()
        self.depth_rtsp = RtspSystem()
        self.app_pipeline = {}
        self.appsrc = {}
        Gst.init(None)
        for rtsp in [(self.rgb_rtsp, 'rgb', socket_rgb_path), (self.depth_rtsp, 'depth', socket_depth_path)]:
          rtsp, name, socket = rtsp
          rtsp.set_shared(True)
          rtsp.start()
          self.get_mount_points().add_factory(f"/{name}", rtsp)
          self.app_pipeline[name] = self.start_app_pipeline(socket)
          self.appsrc[name] = self.app_pipeline[name].get_child_by_name('source')
        self.attach(None)



        # MCM thread
        t2 = threading.Thread(target=check_streams)
        t2.start()
        GLib.timeout_add_seconds(2, self.timeout)




    def timeout(self):
      pool = self.get_session_pool()
      pool.cleanup()
      return True

    def send_data(self, kind, data):
        retval = self.appsrc[kind].emit('push-buffer', Gst.Buffer.new_wrapped(data))
        if retval != Gst.FlowReturn.OK:
          print("buffer full?")


    def start_app_pipeline(self, file):
       launch_str = app_pipeline.format(file)
       print(launch_str)
       pipeline = Gst.parse_launch(launch_str)
       pipeline.set_state(Gst.State.PLAYING)
       print("playing")
       return pipeline



for socket in [socket_rgb_path, socket_depth_path]:
  if os.path.exists(socket):
    os.remove(socket)


# Create pipeline
pipeline = dai.Pipeline()

camRgb = pipeline.create(dai.node.ColorCamera)
camRgb.setBoardSocket(dai.CameraBoardSocket.CAM_A)
camRgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)

rgbEnc = pipeline.create(dai.node.VideoEncoder)
rgbEncOut = pipeline.create(dai.node.XLinkOut)
rgbEncOut.setStreamName('rgbout')
rgbEnc.setDefaultProfilePreset(25, dai.VideoEncoderProperties.Profile.H264_MAIN)
camRgb.video.link(rgbEnc.input)
rgbEnc.bitstream.link(rgbEncOut.input)

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
    depth = device.getOutputQueue(name="enc", maxSize=30, blocking=True)
    rgb = device.getOutputQueue(name="rgbout", maxSize=30, blocking=True)

    print("RTSP stream available at rtsp://<server-ip>:8554/preview")
    print("Press Ctrl+C to stop encoding...")

    try:
        while True:
            depthData = depth.get().getData()
            server.send_data('depth', depthData)
            rgbData = rgb.get().getData()
            server.send_data('rgb', rgbData)
    except KeyboardInterrupt:
        # Keyboard interrupt (Ctrl + C) detected
        pass