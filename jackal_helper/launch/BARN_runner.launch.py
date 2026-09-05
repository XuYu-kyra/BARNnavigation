import os
import yaml

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction, SetEnvironmentVariable
from launch.actions import LogInfo, Shutdown, TimerAction, ExecuteProcess, GroupAction, RegisterEventHandler
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution

from launch_ros.actions import Node, SetRemap
from launch_ros.parameter_descriptions import ParameterValue

from jackal_helper.utils import get_pkg_src_path

"""Launch gz simulation, ros-gz-bridge, jackal, BARN simulation runner, and (rviz2/gz gui) optionally."""

# TODO: integrate use_sim_time throughout

ARGUMENTS = [
    DeclareLaunchArgument('rviz', default_value='false',
                          choices=['true', 'false'], description='Start rviz.'),
    DeclareLaunchArgument('gui', default_value='false',
                          choices=['true', 'false'], description='Start gazebo gui.'),
    DeclareLaunchArgument('world_idx', default_value='0',
                          description='BARN World Index: [0-299].'),
    DeclareLaunchArgument('setup_path',
                          default_value=PathJoinSubstitution([get_pkg_src_path(jackal_pkg=True), 'config']),
                          description='Clearpath setup path. The folder which contains robot.yaml & nav2.yaml.'),
    DeclareLaunchArgument('out_file',
                          default_value="out.txt",
                          description='File name which trial results are stored.'),
    DeclareLaunchArgument('timeout',
                          default_value='100',
                          description='Trial timeout time in seconds.'),
    DeclareLaunchArgument('throttle_duration',
                          default_value='1',
                          description='Time interval in seconds for throttling BARN Runner log messages during a trial. Set to 0 or a negative value to disable logging.'),
    DeclareLaunchArgument('nav2_log_level',
                          default_value='WARN',
                          description='Log level passed to the Nav2 stack launched by this benchmark.'),
    DeclareLaunchArgument('scan_fault_enable', default_value='false',
                          choices=['true', 'false'], description='Enable a LiDAR scan fault injector before Nav2.'),
    DeclareLaunchArgument('scan_fault_start', default_value='30.0',
                          description='Seconds after first scan before the LiDAR fault activates.'),
    DeclareLaunchArgument('scan_fault_duration', default_value='8.0',
                          description='Duration in seconds for the LiDAR fault window.'),
    DeclareLaunchArgument('scan_fault_persistent', default_value='false',
                          choices=['true', 'false'], description='Keep the LiDAR fault active from start time until run end.'),
    DeclareLaunchArgument('scan_fault_mode', default_value='mask',
                          choices=['mask', 'dropout'], description='LiDAR fault mode: steady masking or intermittent dropout.'),
    DeclareLaunchArgument('scan_fault_center_deg', default_value='0.0',
                          description='Center angle of the faulted LiDAR sector in degrees.'),
    DeclareLaunchArgument('scan_fault_width_deg', default_value='70.0',
                          description='Angular width of the faulted LiDAR sector in degrees.'),
    DeclareLaunchArgument('scan_fault_dropout_period', default_value='1.0',
                          description='For dropout mode: period in seconds of the dropout cycle.'),
    DeclareLaunchArgument('scan_fault_dropout_duty', default_value='0.5',
                          description='For dropout mode: fraction of each cycle spent dropping the sector.'),
    DeclareLaunchArgument('odom_fault_enable', default_value='false',
                          choices=['true', 'false'], description='Enable an odometry fault injector before Nav2.'),
    DeclareLaunchArgument('odom_fault_start', default_value='20.0',
                          description='Seconds after first odom sample before the odometry fault activates.'),
    DeclareLaunchArgument('odom_fault_duration', default_value='20.0',
                          description='Duration in seconds for the odometry fault window.'),
    DeclareLaunchArgument('odom_fault_linear_scale', default_value='1.08',
                          description='Scale factor applied to odometry translation increments during the fault.'),
    DeclareLaunchArgument('odom_fault_yaw_rate_bias_deg_s', default_value='1.5',
                          description='Additional yaw-rate bias in deg/s injected during the odometry fault.'),
    DeclareLaunchArgument('recovery_enable', default_value='false',
                          choices=['true', 'false'], description='Enable a fault-aware recovery gate after Nav2 velocity smoothing.'),
    DeclareLaunchArgument('recovery_mode', default_value='scale',
                          choices=['scale', 'masking_reorient', 'nav2_masking_recovery', 'dropout_scan_filter', 'closed_loop_selector'], description='Recovery mode: legacy scaling, cmd_vel reorientation, Nav2 action-level masking recovery, dropout scan filtering, or closed-loop classifier-to-policy selector.'),
    DeclareLaunchArgument('recovery_linear_scale', default_value='0.35',
                          description='Linear velocity scale applied by the recovery gate while the scan fault is active.'),
    DeclareLaunchArgument('recovery_angular_scale', default_value='0.50',
                          description='Angular velocity scale applied by the recovery gate while the scan fault is active.'),
    DeclareLaunchArgument('recovery_active_timeout', default_value='1.0',
                          description='Seconds after the last fault-active signal before the recovery gate disengages.'),
    DeclareLaunchArgument('recovery_trigger_policy', default_value='immediate',
                          choices=['immediate', 'progress_stall'], description='For masking_reorient: trigger immediately on fault or after progress stalls.'),
    DeclareLaunchArgument('recovery_trigger_delay', default_value='0.0',
                          description='For masking_reorient: seconds to wait after fault onset before immediate trigger is allowed.'),
    DeclareLaunchArgument('recovery_stall_window', default_value='5.0',
                          description='For masking_reorient: odom window used to detect poor progress.'),
    DeclareLaunchArgument('recovery_stall_distance', default_value='0.15',
                          description='For masking_reorient: maximum odom displacement over stall window that counts as poor progress.'),
    DeclareLaunchArgument('recovery_rotation_deg', default_value='60.0',
                          description='For masking_reorient: active-perception turn angle in degrees.'),
    DeclareLaunchArgument('recovery_angular_speed', default_value='0.45',
                          description='For masking_reorient: in-place turn angular speed in rad/s.'),
    DeclareLaunchArgument('recovery_settle_duration', default_value='1.0',
                          description='For masking_reorient: seconds to hold zero cmd_vel after rotation before releasing Nav2.'),
    DeclareLaunchArgument('recovery_dropout_range_max_ratio_threshold', default_value='0.55',
                          description='For dropout_scan_filter: frontal sector range_max ratio above which a scan phase is rejected.'),
    DeclareLaunchArgument('recovery_dropout_near_range_max_fraction', default_value='0.98',
                          description='For dropout_scan_filter: fraction of range_max used to classify a beam as near max range.'),
    DeclareLaunchArgument('recovery_selector_observation_window', default_value='2.0',
                          description='For closed_loop_selector: seconds of faulted scan observed before latching MASKING/DROPOUT/UNKNOWN.'),
]


def parse_world_idx(world_idx:str)->str:
    world_idx = int(world_idx)
    if world_idx < 300:  # static environment from 0-299
        world_name = f"BARN/world_{world_idx}.world"
        GOAL_DIST = 10
    elif world_idx < 360:  # Dynamic environment from 300-359
        world_name = f"DynaBARN/world_{world_idx - 300}.world"
        GOAL_DIST = 20
    else:
        raise ValueError(f"World index {world_idx} does not exist")

    return world_name, GOAL_DIST


def float_param(name: str) -> ParameterValue:
    """Force numeric launch arguments to ROS double parameters.

    Without this, values such as scan_fault_start:=15 are inferred as integers
    and rclpy rejects them when the node declares a double parameter.
    """
    return ParameterValue(LaunchConfiguration(name), value_type=float)


def launch_ros_gazebo(context, *args, **kwargs):
    """
    Launches Gazebo server + gui, sets up resources path, and launches ros-gz-bridge.
    """
    pkg_jackal_helper = get_package_share_directory('jackal_helper')
    pkg_ros_gz_sim = get_package_share_directory('ros_gz_sim')

    gz_sim_launch = PathJoinSubstitution([pkg_ros_gz_sim, 'launch', 'gz_sim.launch.py'])
    gui_config = PathJoinSubstitution([pkg_jackal_helper, 'config', 'gui.config'])

    gui_cmd = "" if LaunchConfiguration('gui').perform(context) == 'true' else " -s"
    world_name = parse_world_idx(LaunchConfiguration("world_idx").perform(context))[0]
    world_path = os.path.join(pkg_jackal_helper, "worlds", world_name)

    gz_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([gz_sim_launch]),
        launch_arguments=[
            ('gz_args', [world_path,
                        gui_cmd,
                         ' -r -v 0',
                         ' --gui-config ',
                         gui_config]),
        ]
    )

    clock_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='clock_bridge',
        arguments=[
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            '/world/default/control@ros_gz_interfaces/srv/ControlWorld',
            '/world/default/set_pose@ros_gz_interfaces/srv/SetEntityPose',
            '/robot/touched@std_msgs/msg/Bool@gz.msgs.Boolean',
            '/model/robot/pose@tf2_msgs/msg/TFMessage@gz.msgs.Pose_V',
            '--ros-args', '--log-level', 'WARN'
        ],
        output='screen'
    )

    return [gz_sim, clock_bridge]


def spawn_jackal(context, *args, **kwargs):
    spawner_launch_path = PathJoinSubstitution([get_package_share_directory('clearpath_gz'), 'launch', 'robot_spawn.launch.py'])

    world_name = parse_world_idx(LaunchConfiguration('world_idx').perform(context))[0]
    remap_scan_topic = SetRemap(src='/sensors/lidar2d_0/scan', dst='/front/scan')

    robot_spawn = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([spawner_launch_path]),
        launch_arguments=[
            ('use_sim_time', 'true'),
            ('setup_path', LaunchConfiguration('setup_path')),
            ('world', world_name),
            ('rviz', LaunchConfiguration('rviz')),
            ('generate', 'true'),
            ('x', '2.0'),
            ('y', '2.0'),
            ('z', '0.3')]
    )

    return [remap_scan_topic, robot_spawn]


def launch_scan_fault_injector(context, *args, **kwargs):
    fault_log = LogInfo(
        msg=[
            '>>>>>>>>> LiDAR fault injector enabled: start=',
            LaunchConfiguration('scan_fault_start'),
            's duration=',
            LaunchConfiguration('scan_fault_duration'),
            's persistent=',
            LaunchConfiguration('scan_fault_persistent'),
            ' mode=',
            LaunchConfiguration('scan_fault_mode'),
            ' width=',
            LaunchConfiguration('scan_fault_width_deg'),
            'deg dropout_period=',
            LaunchConfiguration('scan_fault_dropout_period'),
            's dropout_duty=',
            LaunchConfiguration('scan_fault_dropout_duty')
        ],
        condition=IfCondition(LaunchConfiguration('scan_fault_enable'))
    )

    fault_injector = Node(
        package='jackal_helper',
        executable='laser_scan_fault_injector.py',
        name='laser_scan_fault_injector',
        output='screen',
        emulate_tty=True,
        condition=IfCondition(LaunchConfiguration('scan_fault_enable')),
        parameters=[
            {'use_sim_time': True},
            {'input_topic': '/front/scan'},
            {'output_topic': '/front/scan_faulted'},
            {'fault_start_s': float_param('scan_fault_start')},
            {'fault_duration_s': float_param('scan_fault_duration')},
            {'fault_persistent': LaunchConfiguration('scan_fault_persistent')},
            {'fault_mode': LaunchConfiguration('scan_fault_mode')},
            {'sector_center_deg': float_param('scan_fault_center_deg')},
            {'sector_width_deg': float_param('scan_fault_width_deg')},
            {'replacement_value': 'range_max'},
            {'dropout_period_s': float_param('scan_fault_dropout_period')},
            {'dropout_duty_cycle': float_param('scan_fault_dropout_duty')},
            {'fault_active_topic': '/fault/scan_active'},
        ]
    )

    return [fault_log, fault_injector]



def launch_odom_fault_injector(context, *args, **kwargs):
    fault_log = LogInfo(
        msg=[
            '>>>>>>>>> Odometry fault injector enabled: start=',
            LaunchConfiguration('odom_fault_start'),
            's duration=',
            LaunchConfiguration('odom_fault_duration'),
            's linear_scale=',
            LaunchConfiguration('odom_fault_linear_scale'),
            ' yaw_rate_bias_deg_s=',
            LaunchConfiguration('odom_fault_yaw_rate_bias_deg_s')
        ],
        condition=IfCondition(LaunchConfiguration('odom_fault_enable'))
    )

    fault_injector = Node(
        package='jackal_helper',
        executable='odometry_fault_injector.py',
        name='odometry_fault_injector',
        output='screen',
        emulate_tty=True,
        condition=IfCondition(LaunchConfiguration('odom_fault_enable')),
        parameters=[
            {'use_sim_time': True},
            {'input_topic': '/platform/odom/filtered'},
            {'output_topic': '/platform/odom/filtered_faulted'},
            {'fault_start_s': float_param('odom_fault_start')},
            {'fault_duration_s': float_param('odom_fault_duration')},
            {'linear_scale': float_param('odom_fault_linear_scale')},
            {'yaw_rate_bias_deg_s': float_param('odom_fault_yaw_rate_bias_deg_s')},
        ]
    )

    return [fault_log, fault_injector]


def launch_recovery_gate(context, *args, **kwargs):
    mode = LaunchConfiguration('recovery_mode').perform(context)
    relative_goal_distance = float(parse_world_idx(LaunchConfiguration('world_idx').perform(context))[1])
    log_action = LogInfo(
        msg=[
            '>>>>>>>>> Recovery enabled: mode=',
            LaunchConfiguration('recovery_mode'),
            ' linear_scale=',
            LaunchConfiguration('recovery_linear_scale'),
            ' angular_scale=',
            LaunchConfiguration('recovery_angular_scale'),
            ' rotation_deg=',
            LaunchConfiguration('recovery_rotation_deg'),
            ' active_timeout=',
            LaunchConfiguration('recovery_active_timeout'),
            's'
        ],
        condition=IfCondition(LaunchConfiguration('recovery_enable'))
    )

    if mode == 'masking_reorient':
        gate_node = Node(
            package='jackal_helper',
            executable='masking_reorientation_recovery.py',
            name='masking_reorientation_recovery',
            output='screen',
            emulate_tty=True,
            condition=IfCondition(LaunchConfiguration('recovery_enable')),
            parameters=[
                {'use_sim_time': True},
                {'input_topic': '/cmd_vel_recovery_in'},
                {'output_topic': '/cmd_vel'},
                {'fault_active_topic': '/fault/scan_active'},
                {'odom_topic': '/platform/odom/filtered'},
                {'trigger_policy': LaunchConfiguration('recovery_trigger_policy')},
                {'trigger_delay_s': float_param('recovery_trigger_delay')},
                {'stall_window_s': float_param('recovery_stall_window')},
                {'stall_distance_m': float_param('recovery_stall_distance')},
                {'rotation_angle_deg': float_param('recovery_rotation_deg')},
                {'angular_speed_rad_s': float_param('recovery_angular_speed')},
                {'settle_duration_s': float_param('recovery_settle_duration')},
                {'fault_active_timeout_s': float_param('recovery_active_timeout')},
            ]
        )
    elif mode == 'nav2_masking_recovery':
        gate_node = Node(
            package='jackal_helper',
            executable='masking_nav2_recovery_supervisor.py',
            name='masking_nav2_recovery_supervisor',
            output='screen',
            emulate_tty=True,
            condition=IfCondition(LaunchConfiguration('recovery_enable')),
            parameters=[
                {'use_sim_time': True},
                {'fault_active_topic': '/fault/scan_active'},
                {'odom_topic': '/platform/odom/filtered'},
                {'navigate_action_name': '/navigate_to_pose'},
                {'spin_action_name': '/spin'},
                {'local_clear_service': '/local_costmap/clear_entirely_local_costmap'},
                {'global_clear_service': '/global_costmap/clear_entirely_global_costmap'},
                {'trigger_policy': LaunchConfiguration('recovery_trigger_policy')},
                {'trigger_delay_s': float_param('recovery_trigger_delay')},
                {'stall_window_s': float_param('recovery_stall_window')},
                {'stall_distance_m': float_param('recovery_stall_distance')},
                {'spin_angle_deg': float_param('recovery_rotation_deg')},
                {'spin_time_allowance_s': 20.0},
                {'settle_duration_s': float_param('recovery_settle_duration')},
                {'goal_frame_id': 'odom'},
                {'goal_x': relative_goal_distance},
                {'goal_y': 0.0},
                {'goal_yaw_deg': 0.0},
                {'fault_active_timeout_s': float_param('recovery_active_timeout')},
            ]
        )
    elif mode == 'dropout_scan_filter':
        gate_node = Node(
            package='jackal_helper',
            executable='dropout_scan_recovery_filter.py',
            name='dropout_scan_recovery_filter',
            output='screen',
            emulate_tty=True,
            condition=IfCondition(LaunchConfiguration('recovery_enable')),
            parameters=[
                {'use_sim_time': True},
                {'input_topic': '/front/scan_faulted'},
                {'output_topic': '/front/scan_recovered'},
                {'fault_active_topic': '/fault/scan_active'},
                {'filter_active_topic': '/fault/dropout_filter_active'},
                {'require_enable': False},
                {'sector_center_deg': float_param('scan_fault_center_deg')},
                {'sector_width_deg': float_param('scan_fault_width_deg')},
                {'range_max_ratio_threshold': float_param('recovery_dropout_range_max_ratio_threshold')},
                {'near_range_max_fraction': float_param('recovery_dropout_near_range_max_fraction')},
            ]
        )
    elif mode == 'closed_loop_selector':
        selector_node = Node(
            package='jackal_helper',
            executable='scan_fault_policy_selector.py',
            name='scan_fault_policy_selector',
            output='screen',
            emulate_tty=True,
            condition=IfCondition(LaunchConfiguration('recovery_enable')),
            parameters=[
                {'use_sim_time': True},
                {'scan_topic': '/front/scan_faulted'},
                {'fault_active_topic': '/fault/scan_active'},
                {'fault_type_topic': '/fault/type_estimated'},
                {'dropout_enable_topic': '/recovery/dropout_filter_enable'},
                {'masking_enable_topic': '/recovery/masking_monitor_enable'},
                {'observation_window_s': float_param('recovery_selector_observation_window')},
                {'sector_center_deg': float_param('scan_fault_center_deg')},
                {'sector_width_deg': float_param('scan_fault_width_deg')},
            ]
        )
        dropout_filter_node = Node(
            package='jackal_helper',
            executable='dropout_scan_recovery_filter.py',
            name='dropout_scan_recovery_filter',
            output='screen',
            emulate_tty=True,
            condition=IfCondition(LaunchConfiguration('recovery_enable')),
            parameters=[
                {'use_sim_time': True},
                {'input_topic': '/front/scan_faulted'},
                {'output_topic': '/front/scan_recovered'},
                {'fault_active_topic': '/fault/scan_active'},
                {'enable_topic': '/recovery/dropout_filter_enable'},
                {'filter_active_topic': '/fault/dropout_filter_active'},
                {'require_enable': True},
                {'sector_center_deg': float_param('scan_fault_center_deg')},
                {'sector_width_deg': float_param('scan_fault_width_deg')},
                {'range_max_ratio_threshold': float_param('recovery_dropout_range_max_ratio_threshold')},
                {'near_range_max_fraction': float_param('recovery_dropout_near_range_max_fraction')},
            ]
        )
        masking_supervisor_node = Node(
            package='jackal_helper',
            executable='masking_nav2_recovery_supervisor.py',
            name='masking_nav2_recovery_supervisor',
            output='screen',
            emulate_tty=True,
            condition=IfCondition(LaunchConfiguration('recovery_enable')),
            parameters=[
                {'use_sim_time': True},
                {'fault_active_topic': '/fault/scan_active'},
                {'enable_topic': '/recovery/masking_monitor_enable'},
                {'require_enable': True},
                {'odom_topic': '/platform/odom/filtered'},
                {'navigate_action_name': '/navigate_to_pose'},
                {'spin_action_name': '/spin'},
                {'local_clear_service': '/local_costmap/clear_entirely_local_costmap'},
                {'global_clear_service': '/global_costmap/clear_entirely_global_costmap'},
                {'trigger_policy': LaunchConfiguration('recovery_trigger_policy')},
                {'trigger_delay_s': float_param('recovery_trigger_delay')},
                {'stall_window_s': float_param('recovery_stall_window')},
                {'stall_distance_m': float_param('recovery_stall_distance')},
                {'spin_angle_deg': float_param('recovery_rotation_deg')},
                {'spin_time_allowance_s': 20.0},
                {'settle_duration_s': float_param('recovery_settle_duration')},
                {'goal_frame_id': 'odom'},
                {'goal_x': relative_goal_distance},
                {'goal_y': 0.0},
                {'goal_yaw_deg': 0.0},
                {'fault_active_timeout_s': float_param('recovery_active_timeout')},
            ]
        )
        return [log_action, selector_node, dropout_filter_node, masking_supervisor_node]
    else:
        gate_node = Node(
            package='jackal_helper',
            executable='fault_aware_cmdvel_gate.py',
            name='fault_aware_cmdvel_gate',
            output='screen',
            emulate_tty=True,
            condition=IfCondition(LaunchConfiguration('recovery_enable')),
            parameters=[
                {'use_sim_time': True},
                {'input_topic': '/cmd_vel_recovery_in'},
                {'output_topic': '/cmd_vel'},
                {'fault_active_topic': '/fault/scan_active'},
                {'linear_scale': float_param('recovery_linear_scale')},
                {'angular_scale': float_param('recovery_angular_scale')},
                {'active_timeout_s': float_param('recovery_active_timeout')},
            ]
        )

    return [log_action, gate_node]


def launch_navigation_stack(context, *args, **kwargs):
    scan_fault_enabled = LaunchConfiguration('scan_fault_enable').perform(context) == 'true'
    recovery_enabled = LaunchConfiguration('recovery_enable').perform(context) == 'true'
    recovery_mode = LaunchConfiguration('recovery_mode').perform(context)
    if scan_fault_enabled and recovery_enabled and recovery_mode in ('dropout_scan_filter', 'closed_loop_selector'):
        scan_topic = '/front/scan_recovered'
    elif scan_fault_enabled:
        scan_topic = '/front/scan_faulted'
    else:
        scan_topic = '/front/scan'
    odom_topic = 'platform/odom/filtered_faulted' if LaunchConfiguration('odom_fault_enable').perform(context) == 'true' else 'platform/odom/filtered'
    recovery_intercepts_cmd_vel = recovery_enabled and recovery_mode in ('scale', 'masking_reorient')
    final_cmd_vel_topic = '/cmd_vel_recovery_in' if recovery_intercepts_cmd_vel else '/cmd_vel'

    nav2_launch_path = PathJoinSubstitution([get_package_share_directory('jackal_helper'), 'launch', 'nav2_bringup.launch.py'])
    nav2_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([nav2_launch_path]),
        launch_arguments=[
            ('use_sim_time', 'true'),
            ('setup_path', LaunchConfiguration('setup_path')),
            ('scan_topic', scan_topic),
            ('odom_topic', odom_topic),
            ('final_cmd_vel_topic', final_cmd_vel_topic),
            ('nav2_params_file', 'nav2.yaml'),
            ('log_level', LaunchConfiguration('nav2_log_level'))
            ]
    )

    nav2_exit_handler = RegisterEventHandler(
        OnProcessExit(
            target_action=lambda action: action.name == 'bt_navigator',
            on_exit=[Shutdown()]
        )
    )

    relative_goal_distance = parse_world_idx(LaunchConfiguration("world_idx").perform(context))[1]
    goal = {
        "pose": {
            "header": {"frame_id": "odom"},
            "pose": {
                "position": {
                    "x": relative_goal_distance,
                    "y": 0.0,
                    "z": 0.0,
                },
                "orientation": {"w": 1.0},
            }
        }
    }
    goal_str = yaml.dump(goal, default_flow_style=True, width=float("inf")).rstrip("\n")

    publish_goal = TimerAction(
        period=10.0,
        actions=[
            LogInfo(msg=">>>>>>>>> Publishing Nav2 goal... "),
            ExecuteProcess(
                cmd=[
                    'ros2', 'action', 'send_goal',
                    '/navigate_to_pose',
                    'nav2_msgs/action/NavigateToPose',
                    goal_str
                ],
                output='log'
            )
        ]
    )

    return [nav2_launch, nav2_exit_handler, publish_goal]


def generate_launch_description():
    set_logging_format = SetEnvironmentVariable(name="RCUTILS_CONSOLE_OUTPUT_FORMAT", value="[{severity}] [{name}]: {message}")

    BARN_runner_node = TimerAction(
        period=10.0,
        actions=[
            LogInfo(msg=">>>>>>>>> Starting BARN Runner node..."),
            Node(
                package="jackal_helper",
                executable="barn_runner.py",
                output='screen',
                emulate_tty=True,
                parameters=[
                    {'world_idx': LaunchConfiguration('world_idx')},
                    {'out_file': LaunchConfiguration('out_file')},
                    {'timeout': LaunchConfiguration('timeout')},
                    {'logging_throttle_duration_s': LaunchConfiguration('throttle_duration')}
                    ],
                on_exit=[
                    LogInfo(msg=">>>>>>>>> Shutting down in 5 seconds..."),
                    TimerAction(period=5.0, actions=[Shutdown(), ExecuteProcess(cmd=['pkill', '-9', '-f', '\'gz sim\''], shell=True)]),
                    ],
            )
        ]
    )

    nav_stack = TimerAction(
        period=15.0,
        actions=[LogInfo(msg=">>>>>>>>> Launching Nav2..."), OpaqueFunction(function=launch_navigation_stack)]
    )

    ld = LaunchDescription(ARGUMENTS)
    ld.add_action(set_logging_format)
    ld.add_action(OpaqueFunction(function=launch_ros_gazebo))
    ld.add_action(OpaqueFunction(function=spawn_jackal))
    ld.add_action(OpaqueFunction(function=launch_scan_fault_injector))
    ld.add_action(OpaqueFunction(function=launch_odom_fault_injector))
    ld.add_action(OpaqueFunction(function=launch_recovery_gate))
    ld.add_action(BARN_runner_node)
    ld.add_action(nav_stack)
    return ld
