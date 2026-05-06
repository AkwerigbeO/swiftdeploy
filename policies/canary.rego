package canary

default allow := true

allow := false if {
    input.error_rate > input.max_error_rate
}

allow := false if {
    input.p99_latency > input.max_latency
}

reasons contains msg if {
    input.error_rate > input.max_error_rate
    msg := "Error rate too high"
}

reasons contains msg if {
    input.p99_latency > input.max_latency
    msg := "Latency too high"
}