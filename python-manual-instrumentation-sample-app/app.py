from config import *

import random_metrics
import requests
import random
import boto3
import os
from flask import Flask, request, render_template
from random import randint

#Import libraries for instrumentation
from opentelemetry import propagate, trace, metrics


# Exporter Libraries
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Metrics Library
from opentelemetry.metrics import CallbackOptions, Observation

# SDK Libraries
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.extension.aws.trace import AwsXRayIdGenerator
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

# Propogators Library
from opentelemetry.propagators.aws import AwsXRayPropagator
from opentelemetry.propagators.aws.aws_xray_propagator import (
    TRACE_ID_DELIMITER,
    TRACE_ID_FIRST_PART_LENGTH,
    TRACE_ID_VERSION,
)

# Instrumentation Libraries
# These provide pre-build instrumentation options for popular libaries such as Flask or Boto
from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

# Starting Flask app
app = Flask(__name__)

# Generate config from config file
cfg = create_config('config.yaml')

"""
TRACES & REQUEST BASED METRICS
"""
# Global variable to keep track of the total number of API requests
n = 0


# First we set up a global tracer and meter. Any function from here forward can re-use the tracer and meter to generate either traces or metrics. We can also generate unique tracers within function.
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# We can set up a baseline of instrumentation by brining in instrumenation libararies for the pakages we are using. These give a good baseline to start from.
def setup_instrumentation():
    BotocoreInstrumentor().instrument()
    FlaskInstrumentor().instrument_app(app)
    RequestsInstrumentor().instrument()

# Setting up opentelemetry, we will pass in our global tracer and meter we created earlier.
def setup_opentelemetry(tracer, meter):
    # Set up AWS X-Ray Propagator, we do this because we need to create trace-ids in a format that x-ray can understand.
    propagate.set_global_textmap(AwsXRayPropagator())
    
    # Service name is required for most backends. We can try to grab additional attributes from the environment.
    resource_attributes = { 'service.name': 'python-manual-instrumentation-sample-app' }
    if (os.environ.get("OTEL_RESOURCE_ATTRIBUTES")):
        resource_attributes = None
    resource = Resource.create(attributes=resource_attributes)

    # Setting up Tracer Provider, we will batch up spans and then send them to an exporter. We also need to add the resources we defined earlier and use our x-ray generator.
    processor = BatchSpanProcessor(OTLPSpanExporter())
    tracer_provider = TracerProvider(
        resource=resource, 
        active_span_processor=processor,
        id_generator=AwsXRayIdGenerator())
    
    # Initalize the tracer provider with the configuration defined above.
    trace.set_tracer_provider(tracer_provider)
    
    # Name the tracer, for the purposes of the demo we can just use __name__ but best practice would be to use the name of the instrumenting module.
    tracer = trace.get_tracer(__name__)

    # Setting up Metrics export, here we will export every 1000 ms
    metric_reader = PeriodicExportingMetricReader(exporter=OTLPMetricExporter(), export_interval_millis=1000)
    metric_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    
    #Initialize the meter.
    metrics.set_meter_provider(metric_provider)
    meter = metrics.get_meter(__name__)

common_attributes = { 'signal': 'metric', 'language': 'python-manual-instrumentation', 'metricType': 'request' }


#Try to add some relevant environment variables, these get added as attributes to our traces.
testingId = ""
if (os.environ.get("INSTANCE_ID")):
            testingId = "_" + os.environ["INSTANCE_ID"]

# update_total_bytes_sent updates the metric with a random value between 0 and 1024
def update_total_bytes_sent():
    min = 0 
    max = 1024
    total_bytes_sent.add(random.randint(min,max), attributes=common_attributes)

# update latency time updates the metric with a value between 0 and 512
def update_latency_time():
    min = 0
    max = 512
    latency_time.record(random.randint(min, max), attributes=common_attributes)
    
#Call back that will give us a metric for number of downstream api requests made by the SDK.
def api_requests_callback(options: CallbackOptions):
    global n
    n += 1
    add_api_request = Observation(value=n, attributes=common_attributes)
    print("api_requests called by SDK")
    yield add_api_request
    
#Try to add some relevant environment variables, these get added as attributes to our traces.
testingId = ""
if (os.environ.get("INSTANCE_ID")):
            testingId = "_" + os.environ["INSTANCE_ID"]


# register total bytes sent counter. Here is where we actually create the counter for bytes sent metric we generated earlier.
total_bytes_sent=meter.create_counter(
    name="total_bytes_sent" + testingId,
    description="Keeps a sum of the total amount of bytes sent while application is alive",
    unit='By'
)

# register api requests observable counter.
total_api_requests=meter.create_observable_counter(
    name="total_api_requests" + testingId,
    callbacks=[api_requests_callback],
    description="Increments by one every time a sampleapp endpoint is used",
    unit='1'
)

# registers latency time histogram. A histogram is an aggregation of all reported measurements over a time interval.
latency_time=meter.create_histogram(
    name="latency_time" + testingId,
    description="Measures latency time in buckets of 100, 300 and 500",
    unit='ms'
        )
        
#Create a counter for the dice rolls
roll_counter = meter.create_counter(
    name="dice.rolls",
    description="The number of rolls by roll value",
    )

# Converts otel trace id's to an xray format, we are doing this just so we can see in std out the x-ray trace id as they are generated.
def convert_otel_trace_id_to_xray(otel_trace_id_decimal):
    otel_trace_id_hex = "{:032x}".format(otel_trace_id_decimal)
    x_ray_trace_id = TRACE_ID_DELIMITER.join(
        [
            TRACE_ID_VERSION,
            otel_trace_id_hex[:TRACE_ID_FIRST_PART_LENGTH],
            otel_trace_id_hex[TRACE_ID_FIRST_PART_LENGTH:],
        ]
    )
    return '{{"traceId": "{}"}}'.format(x_ray_trace_id)
    
def roll():
    with tracer.start_as_current_span("roll") as rollspan:
        res = randint(1, 6)
        rollspan.set_attribute("roll.value", res)
        # This adds 1 to the counter for the given roll value
        roll_counter.add(1, {"roll.value": res})
        return res

# Test HTTP instrumentation
@app.route("/outgoing-http-call")
def call_http():
    with tracer.start_as_current_span("outgoing-http-call") as span:

        # Demonstrates setting an attribute, a k/v pairing.
        span.set_attribute("language", "python-manual-instrumentation")
        span.set_attribute("signal", "trace")

        # Demonstrating adding events to the span. Think of events as a primitive log. Good for tracking a meaningful singular point in time.
        span.add_event("Making a request to https://aws.amazon.com/")
        requests.get("https://aws.amazon.com/")

        print("updating bytes sent & latency time...")
        update_total_bytes_sent()
        update_latency_time()

        return app.make_response(
            convert_otel_trace_id_to_xray(
                trace.get_current_span().get_span_context().trace_id
            )
        )


#Create a route that returns a key value pair of credit card: credit_card_number, randomly generate the credit card number
@app.route("/credit-card")
def credit_card():
    with tracer.start_as_current_span("credit-card") as span:
        span.set_attribute("language", "python-manual-instrumentation")
        span.set_attribute("signal", "trace")
        span.add_event("Getting a credit card number")
        credit_card = randint(0000000000000000, 0000000000000000)
        span.set_attribute("credit_card", credit_card)
        print(credit_card)
        return app.make_response(
            convert_otel_trace_id_to_xray(
                trace.get_current_span().get_span_context().trace_id
            )
        )


# Test AWS SDK instrumentation
@app.route("/aws-sdk-call")
def call_aws_sdk():

    with tracer.start_as_current_span("aws-sdk-call") as span:

        span.set_attribute("language", "python-manual-instrumentation")
        span.set_attribute("signal", "trace")

        print("updating bytes sent & latency time...")
        update_total_bytes_sent()
        update_latency_time()

        span.add_event("listing s3 buckets")
        client = boto3.client("s3")
        client.list_buckets()

        return app.make_response(
            convert_otel_trace_id_to_xray(
                trace.get_current_span().get_span_context().trace_id
            )
        )

# when this sample-app is invoked either by itself or a different sample app
@app.route("/outgoing-sampleapp")
def invoke():
    # Call sample apps
    with tracer.start_as_current_span("outgoing-sampleapp-parent") as parent:
        parent.set_attribute("operation.name", "outgoing-sampleapp-call")
        ports = cfg.get("SampleAppPorts")
        if ports:
            for port in ports:
                parent.add_event("Sampleapp detected. Generating nested span.")
                with tracer.start_as_current_span("outgoing-sampleapp-child") as child:
                    uri = f"http://127.0.0.1:{port}/outgoing-sampleapp"
                    print("making a request to: " + uri)
                    r = requests.get(uri)

        # If no sample apps are defined in the config file the app makes a request to amazon.
        else:
            with tracer.start_as_current_span("outgoing-sample-app-no-ports") as child:
                print("no ports configured. making a request to https://aws.amazon.com instead.")
                requests.get("https://aws.amazon.com/")
        
    update_total_bytes_sent()
    update_latency_time()
    
    return app.make_response(
        convert_otel_trace_id_to_xray(
            parent.get_span_context().trace_id
        )
    )

# Test Root Endpoint
@app.route("/")
def root_endpoint():
    return "OK"
    
@app.route("/rolldice")
def roll_dice():
    return str(roll())
    
#setup polling and templates for demo.
@app.route('/poll')
def index():
    with tracer.start_as_current_span("state-poll") as span:
        span.set_attribute("language", "python-manual-instrumentation")
        span.set_attribute("signal", "trace")
        span.set_attribute("page", "poll")
        span.add_event("Taking a poll of the audience.")
        print("Polling for states")
    return render_template('poll.html')

#Generate unique url for demo.
@app.route('/<state>')
def state(state):
    return render_template('state.html', state=state)

#Run the app.
if __name__ == '__main__':
    # setting up instrumentation & opentelemetry
    setup_instrumentation()
    setup_opentelemetry(tracer, meter)
    rmc = random_metrics.RandomMetricCollector()
    rmc.register_metrics_client(cfg)
    app.run(host=cfg['Host'], port=cfg['Port'])

