#!/bin/bash

# 视频尾帧提取脚本 - WSL环境专用
# 用法: ./extract_frame.sh "C:\\Users\\39845\\Downloads\\video.mp4" [输出文件名]

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查参数
if [ $# -eq 0 ]; then
    echo -e "${RED}错误: 请提供视频文件路径${NC}"
    echo "用法: $0 \"C:\\Users\\39845\\Downloads\\video.mp4\" [输出文件名]"
    exit 1
fi

VIDEO_PATH="$1"
OUTPUT_FILE="$2"

# 将Windows路径转换为WSL路径
convert_path() {
    local win_path="$1"
    # 移除引号
    win_path=$(echo "$win_path" | sed 's/^"\(.*\)"$/\1/')
    
    # 转换 C:\ 格式到 /mnt/c/ 格式
    if [[ "$win_path" =~ ^[A-Za-z]:\\\\ ]]; then
        drive=$(echo "${win_path:0:1}" | tr '[:upper:]' '[:lower:]')
        path="${win_path:3}"
        path=$(echo "$path" | sed 's/\\\\/\//g')
        echo "/mnt/$drive/$path"
    else
        echo "$win_path"
    fi
}

# 检查ffmpeg是否安装
check_ffmpeg() {
    if ! command -v ffmpeg &> /dev/null; then
        echo -e "${RED}错误: ffmpeg 未安装${NC}"
        echo "请运行: sudo apt update && sudo apt install ffmpeg"
        exit 1
    fi
    
    if ! command -v ffprobe &> /dev/null; then
        echo -e "${RED}错误: ffprobe 未安装${NC}"
        echo "请运行: sudo apt update && sudo apt install ffmpeg"
        exit 1
    fi
}

# 获取视频信息
get_video_duration() {
    local video_path="$1"
    ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$video_path" 2>/dev/null
}

# 主函数
main() {
    echo -e "${YELLOW}视频尾帧提取工具${NC}"
    echo "================================"
    
    # 检查依赖
    check_ffmpeg
    
    # 转换路径
    WSL_VIDEO_PATH=$(convert_path "$VIDEO_PATH")
    echo -e "原始路径: ${YELLOW}$VIDEO_PATH${NC}"
    echo -e "WSL路径:  ${YELLOW}$WSL_VIDEO_PATH${NC}"
    
    # 检查文件是否存在
    if [ ! -f "$WSL_VIDEO_PATH" ]; then
        echo -e "${RED}错误: 视频文件不存在: $WSL_VIDEO_PATH${NC}"
        exit 1
    fi
    
    # 获取视频信息
    echo -e "\n${YELLOW}获取视频信息...${NC}"
    DURATION=$(get_video_duration "$WSL_VIDEO_PATH")
    if [ -z "$DURATION" ]; then
        echo -e "${RED}错误: 无法获取视频时长${NC}"
        exit 1
    fi
    
    echo "视频时长: ${DURATION}秒"
    
    # 计算提取时间点（距离结尾0.1秒）
    EXTRACT_TIME=$(echo "$DURATION - 0.1" | bc -l)
    if (( $(echo "$EXTRACT_TIME < 0" | bc -l) )); then
        EXTRACT_TIME=0
    fi
    echo "提取时间点: ${EXTRACT_TIME}秒"
    
    # 确定输出文件名
    if [ -z "$OUTPUT_FILE" ]; then
        BASENAME=$(basename "$WSL_VIDEO_PATH")
        FILENAME="${BASENAME%.*}"
        OUTPUT_FILE="${FILENAME}_last_frame.jpg"
    fi
    
    echo -e "输出文件: ${GREEN}$OUTPUT_FILE${NC}"
    
    # 提取尾帧
    echo -e "\n${YELLOW}提取尾帧...${NC}"
    ffmpeg -y -ss "$EXTRACT_TIME" -i "$WSL_VIDEO_PATH" -frames:v 1 -q:v 2 "$OUTPUT_FILE" 2>/dev/null
    
    if [ $? -eq 0 ] && [ -f "$OUTPUT_FILE" ]; then
        FILE_SIZE=$(stat -c%s "$OUTPUT_FILE")
        echo -e "${GREEN}✅ 提取成功!${NC}"
        echo -e "输出文件: ${GREEN}$(realpath "$OUTPUT_FILE")${NC}"
        echo -e "文件大小: ${FILE_SIZE} bytes"
    else
        echo -e "${RED}❌ 提取失败${NC}"
        exit 1
    fi
}

# 运行主函数
main "$@"

