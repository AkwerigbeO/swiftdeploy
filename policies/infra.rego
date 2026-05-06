package infra

default allow := true

allow := false if {
    input.disk_free < input.min_disk
}

allow := false if {
    input.cpu_load > input.max_cpu
}

reasons contains msg if {
    input.disk_free < input.min_disk
    msg := "Disk space below minimum threshold"
}

reasons contains msg if {
    input.cpu_load > input.max_cpu
    msg := "CPU load too high"
}