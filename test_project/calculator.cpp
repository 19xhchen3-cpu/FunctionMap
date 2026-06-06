/* 计算器模块 - 演示C++函数调用关系 */

#include <string>
#include <vector>

// ===== 基础运算函数 =====

int add(int a, int b) {
    return a + b;
}

int subtract(int a, int b) {
    return a - b;
}

int multiply(int a, int b) {
    return a * b;
}

double divide(double a, double b) {
    if (b == 0.0) {
        return 0.0;
    }
    return a / b;
}

// ===== 统计函数 =====

int sum_array(const std::vector<int>& arr) {
    int total = 0;
    for (size_t i = 0; i < arr.size(); i++) {
        total = add(total, arr[i]);
    }
    return total;
}

double average(const std::vector<int>& arr) {
    int sum = sum_array(arr);
    double count = static_cast<double>(arr.size());
    return divide(static_cast<double>(sum), count);
}

// ===== 高级运算 =====

int factorial(int n) {
    if (n <= 1) {
        return 1;
    }
    return multiply(n, factorial(n - 1));  // 递归调用
}

int modulo_add(int a, int b, int mod) {
    int sum = add(a, b);
    return sum % mod;
}

double calculate_expression(const std::vector<int>& nums, const std::string& op) {
    if (op == "sum") {
        return static_cast<double>(sum_array(nums));
    } else if (op == "avg") {
        return average(nums);
    } else if (op == "fact") {
        if (!nums.empty()) {
            return static_cast<double>(factorial(nums[0]));
        }
    }
    return 0.0;
}

// ===== 字符串辅助 =====

std::string format_result(const std::string& expr, double result) {
    std::string output = expr + " = ";
    output += std::to_string(result);
    return output;
}

void print_results(const std::vector<double>& results) {
    for (size_t i = 0; i < results.size(); i++) {
        format_result("result[" + std::to_string(i) + "]", results[i]);
    }
}
