/* 传感器模块 - 演示C语言函数调用关系 */

#include <stdio.h>
#include <stdlib.h>
#include <math.h>

// ===== 底层读取 =====

static int read_raw_sensor(int pin) {
    /* 模拟读取传感器原始值 */
    return pin * 10 + 5;
}

static float calibrate_value(int raw, float offset) {
    float calibrated = (float)raw * 1.05f;
    return calibrated + offset;
}

// ===== 数据过滤 =====

static int is_valid_reading(int value, int min, int max) {
    if (value < min) return 0;
    if (value > max) return 0;
    return 1;
}

static float apply_filter(float current, float previous) {
    /* 简单低通滤波 */
    return current * 0.7f + previous * 0.3f;
}

// ===== 业务逻辑 =====

int init_sensor(int pin) {
    int raw = read_raw_sensor(pin);
    return is_valid_reading(raw, 0, 1000);
}

float read_sensor(int pin) {
    int raw = read_raw_sensor(pin);
    if (!is_valid_reading(raw, 0, 1000)) {
        return -1.0f;
    }
    return calibrate_value(raw, 0.5f);
}

float read_filtered(int pin, float prev_value) {
    float current = read_sensor(pin);
    if (current < 0) {
        return prev_value;
    }
    return apply_filter(current, prev_value);
}

void log_reading(int pin, float value) {
    printf("Sensor %d: %.2f\n", pin, value);
}

void monitor_sensor(int pin, int iterations) {
    float prev = 0.0f;
    for (int i = 0; i < iterations; i++) {
        float val = read_filtered(pin, prev);
        log_reading(pin, val);
        prev = val;
    }
}

// ===== 主入口 =====

int main(int argc, char* argv[]) {
    if (init_sensor(1)) {
        monitor_sensor(1, 5);
    }
    return 0;
}
