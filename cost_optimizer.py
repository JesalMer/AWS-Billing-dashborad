import boto3
import calendar
import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from botocore.exceptions import ClientError

BASE_DIR = os.path.dirname(__file__)
OPTIMIZER_CACHE_FILE = os.path.join(BASE_DIR, "cost_optimizer_cache.json")
CACHE_TTL_SECONDS = 86400  # 24 hours daily cache (user can bypass with Refresh button)


def get_aws_client(service_name, access_key, secret_key, region="us-east-1"):
    """Instantiate a Boto3 client for any AWS service."""
    return boto3.client(
        service_name,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region or "us-east-1"
    )


def extract_resource_tags(tags_input):
    """
    Extract 'Project' and 'Environment' tags from AWS tags format.
    Accepts list of {'Key': '...', 'Value': '...'} or dict.
    """
    project = "Untagged"
    env = "unknown"

    if not tags_input:
        return {"project": project, "environment": env}

    tag_dict = {}
    if isinstance(tags_input, list):
        for t in tags_input:
            k = t.get("Key", "")
            v = t.get("Value", "")
            if k:
                tag_dict[k.lower()] = v
    elif isinstance(tags_input, dict):
        for k, v in tags_input.items():
            tag_dict[k.lower()] = v

    # Check project / client / app keys
    for p_key in ["project", "client", "app", "application", "name"]:
        if p_key in tag_dict and tag_dict[p_key]:
            project = tag_dict[p_key]
            break

    # Check environment keys
    for e_key in ["environment", "env", "stage"]:
        if e_key in tag_dict and tag_dict[e_key]:
            raw_env = tag_dict[e_key].lower()
            if "prod" in raw_env:
                env = "prod"
            elif "stag" in raw_env:
                env = "staging"
            elif "dev" in raw_env or "test" in raw_env:
                env = "dev"
            else:
                env = raw_env
            break

    return {"project": project, "environment": env}


def compute_month_ranges(today=None):
    """Dynamically calculate previous 3 calendar months and current month."""
    if today is None:
        today = date.today()

    current_year = today.year
    current_month = today.month

    curr_start = date(current_year, current_month, 1)
    curr_end = today + timedelta(days=1)
    days_elapsed = today.day
    _, days_in_current_month = calendar.monthrange(current_year, current_month)

    historical_months = []
    y, m = current_year, current_month
    for _ in range(3):
        m -= 1
        if m <= 0:
            m = 12
            y -= 1
        m_start = date(y, m, 1)
        if m == 12:
            m_end = date(y + 1, 1, 1)
        else:
            m_end = date(y, m + 1, 1)
        historical_months.append({
            "start": m_start,
            "end": m_end,
            "label": m_start.strftime("%b %Y"),
            "key": m_start.strftime("%Y-%m"),
            "is_current": False
        })

    historical_months.reverse()

    curr_dict = {
        "start": curr_start,
        "end": curr_end,
        "label": f"{curr_start.strftime('%b %Y')} (MTD)",
        "key": curr_start.strftime("%Y-%m"),
        "is_current": True
    }

    all_months = historical_months + [curr_dict]
    total_start = historical_months[0]["start"]
    total_end = curr_end

    return {
        "all_months": all_months,
        "historical_months": historical_months,
        "current_month": curr_dict,
        "total_start": total_start,
        "total_end": total_end,
        "days_elapsed": days_elapsed,
        "days_in_current_month": days_in_current_month,
        "today": today
    }


def load_optimizer_cache():
    """Load local optimizer disk cache."""
    if not os.path.exists(OPTIMIZER_CACHE_FILE):
        return {}
    try:
        with open(OPTIMIZER_CACHE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_optimizer_cache(cache_data):
    """Save optimizer disk cache."""
    try:
        with open(OPTIMIZER_CACHE_FILE, "w") as f:
            json.dump(cache_data, f, indent=2)
    except Exception as e:
        print(f"[Cost Optimizer Cache] Error saving: {e}")


def get_cached_optimizer_data(account_id):
    """Get cached optimizer analysis if within TTL."""
    cache = load_optimizer_cache()
    acc_cache = cache.get(account_id)
    if not acc_cache:
        return None
    timestamp = acc_cache.get("timestamp", 0)
    if time.time() - timestamp < CACHE_TTL_SECONDS:
        return acc_cache.get("data")
    return None


def set_cached_optimizer_data(account_id, data):
    """Store optimizer analysis in cache with timestamp."""
    cache = load_optimizer_cache()
    cache[account_id] = {
        "timestamp": time.time(),
        "data": data
    }
    save_optimizer_cache(cache)


# =========================================================================
# SCANNER MODULES (SCOPED TO: EC2, EC2-Other, S3, Elastic IP, Cost Explorer)
# =========================================================================

def scan_cost_optimization_hub(access_key, secret_key, region, permissions_log):
    """
    Query AWS Cost Optimization Hub (list_recommendations) if enabled.
    Consolidates AWS-native recommendations first.
    """
    recommendations = []
    try:
        client = get_aws_client("cost-optimization-hub", access_key, secret_key, region)
        resp = client.list_recommendations(maxResults=50)
        items = resp.get("items", [])
        permissions_log["cost_optimization_hub"] = "authorized"

        for item in items:
            res_id = item.get("resourceId", "Unknown")
            res_type = item.get("resourceType", "")
            action_type = item.get("actionType", "")
            sav = float(item.get("estimatedMonthlySavings", 0.0))
            tags = extract_resource_tags(item.get("tags", []))

            service = "EC2"
            if "EBS" in res_type or "Volume" in res_type or "NatGateway" in res_type:
                service = "EC2-Other"
            elif "S3" in res_type or "Bucket" in res_type:
                service = "S3"
            elif "EIP" in res_type or "Address" in res_type:
                service = "Elastic IP"

            headline = f"{action_type} {res_type} {res_id}"
            why_how = (
                f"AWS Cost Optimization Hub detected an active optimization recommendation for {res_id}. "
                f"Action: {action_type}. Estimated monthly savings: ${sav:.2f}."
            )

            recommendations.append({
                "id": f"coh-{res_id}",
                "service": service,
                "resource_id": res_id,
                "headline": headline,
                "action": f"Apply AWS Cost Optimization Hub recommendation: {action_type} on {res_id}",
                "estimated_monthly_saving": round(sav, 2),
                "saving_display": f"~${sav:.2f}/mo",
                "effort": "med",
                "risk_note": "Review workload dependencies and test in staging before applying recommended changes.",
                "why_how_to_fix": why_how,
                "project_tag": tags["project"],
                "environment_tag": tags["environment"],
                "source": "Cost Optimization Hub"
            })
    except ClientError as ce:
        code = ce.response.get("Error", {}).get("Code", "")
        permissions_log["cost_optimization_hub"] = f"denied ({code})"
    except Exception as e:
        permissions_log["cost_optimization_hub"] = f"error ({str(e)})"

    return recommendations


def scan_compute_optimizer(access_key, secret_key, region, permissions_log):
    """
    Query AWS Compute Optimizer for EC2 instance and EBS volume rightsizing.
    """
    recommendations = []
    try:
        client = get_aws_client("compute-optimizer", access_key, secret_key, region)
        # 1. EC2 recommendations
        ec2_res = client.get_ec2_instance_recommendations(maxResults=50)
        permissions_log["compute_optimizer"] = "authorized"

        for rec in ec2_res.get("instanceRecommendations", []):
            finding = rec.get("finding", "")
            if finding in ["OVER_PROVISIONED", "UNDER_PROVISIONED"]:
                inst_id = rec.get("instanceArn", "").split("/")[-1] or rec.get("instanceName", "EC2 Instance")
                curr_type = rec.get("currentInstanceType", "")
                tags = extract_resource_tags(rec.get("tags", []))
                options = rec.get("recommendationOptions", [])

                if options:
                    top_opt = options[0]
                    rec_type = top_opt.get("instanceType", "")
                    # Monthly savings calculation from Compute Optimizer delta
                    saving = float(top_opt.get("estimatedMonthlySavings", {}).get("value", 35.0))
                    if saving <= 0:
                        saving = 25.0

                    headline = f"Downsize over-provisioned EC2 instance {inst_id} ({curr_type} → {rec_type})"
                    action = f"Resize instance {inst_id} from {curr_type} to recommended {rec_type}"
                    why_how = (
                        f"AWS Compute Optimizer analyzed CloudWatch metrics over the lookback period and classified {inst_id} as {finding}. "
                        f"Current type: {curr_type}. Recommended size: {rec_type}.\n\n"
                        f"How to fix:\n"
                        f"1. Open EC2 Console → Instances → select '{inst_id}'.\n"
                        f"2. Stop instance during a maintenance window.\n"
                        f"3. Actions → Instance settings → Change instance type → select '{rec_type}'.\n"
                        f"4. Start the instance and monitor application throughput."
                    )

                    recommendations.append({
                        "id": f"co-ec2-{inst_id}",
                        "service": "EC2",
                        "resource_id": inst_id,
                        "headline": headline,
                        "action": action,
                        "estimated_monthly_saving": round(saving, 2),
                        "saving_display": f"~${saving:.2f}/mo",
                        "effort": "low",
                        "risk_note": "Requires brief instance reboot/stop. Verify memory and CPU peak requirements prior to resizing.",
                        "why_how_to_fix": why_how,
                        "project_tag": tags["project"],
                        "environment_tag": tags["environment"],
                        "source": "Compute Optimizer"
                    })
    except ClientError as ce:
        code = ce.response.get("Error", {}).get("Code", "")
        permissions_log["compute_optimizer"] = f"denied ({code})"
    except Exception as e:
        permissions_log["compute_optimizer"] = f"error ({str(e)})"

    return recommendations


def scan_cost_explorer_recommendations(access_key, secret_key, region, permissions_log):
    """
    Query AWS Cost Explorer for Rightsizing and Savings Plans recommendations.
    """
    recommendations = []
    try:
        client = get_aws_client("ce", access_key, secret_key, region)
        permissions_log["ce_recommendations"] = "authorized"

        # Rightsizing recommendations
        try:
            rs_res = client.get_rightsizing_recommendation(Service="AmazonEC2")
            for rec in rs_res.get("RightsizingRecommendations", []):
                curr_inst = rec.get("CurrentInstance", {})
                inst_id = curr_inst.get("ResourceId", "EC2 Instance")
                tags = extract_resource_tags(curr_inst.get("Tags", []))
                details = rec.get("ModifyRecommendationDetail", {}) or rec.get("TerminateRecommendationDetail", {})
                saving = float(rec.get("EstimatedMonthlySavings", "0.0") or 0.0)
                if saving <= 0:
                    saving = 40.0

                action_str = "Right-size or terminate underutilized EC2 instance"
                if "TargetInstances" in details and details["TargetInstances"]:
                    target_type = details["TargetInstances"][0].get("ResourceDetails", {}).get("EC2ResourceDetails", {}).get("InstanceType", "")
                    action_str = f"Resize instance {inst_id} to {target_type}"

                recommendations.append({
                    "id": f"ce-rs-{inst_id}",
                    "service": "EC2",
                    "resource_id": inst_id,
                    "headline": f"AWS Cost Explorer rightsizing recommendation for {inst_id}",
                    "action": action_str,
                    "estimated_monthly_saving": round(saving, 2),
                    "saving_display": f"~${saving:.2f}/mo",
                    "effort": "low",
                    "risk_note": "Requires brief instance restart. Validate memory utilization before downsizing.",
                    "why_how_to_fix": f"AWS Cost Explorer identified this EC2 instance as underutilized based on historical compute metrics. Potential saving: ${saving:.2f}/month.",
                    "project_tag": tags["project"],
                    "environment_tag": tags["environment"],
                    "source": "Cost Explorer"
                })
        except Exception as e:
            permissions_log["ce_rightsizing"] = str(e)

        # Savings Plans recommendation
        try:
            sp_res = client.get_savings_plans_purchase_recommendation(
                LookbackPeriodInDays="SEVEN_DAYS",
                PaymentOption="NO_UPFRONT",
                SavingsPlansType="COMPUTE_SP",
                TermInYears="ONE_YEAR"
            )
            sp_recs = sp_res.get("SavingsPlansPurchaseRecommendation", {}).get("SavingsPlansPurchaseRecommendationDetails", [])
            for r in sp_recs:
                sav = float(r.get("EstimatedMonthlySavingsAmount", "0.0") or 0.0)
                if sav > 5.0:
                    recommendations.append({
                        "id": "ce-sp-compute",
                        "service": "EC2",
                        "resource_id": "Compute Savings Plan (1-Year)",
                        "headline": "Adopt 1-Year No-Upfront Compute Savings Plan for steady baseline compute",
                        "action": "Purchase recommended AWS Compute Savings Plan to discount steady EC2 and Fargate usage",
                        "estimated_monthly_saving": round(sav, 2),
                        "saving_display": f"~${sav:.2f}/mo",
                        "effort": "low",
                        "risk_note": "1-year hourly spend commitment. Recommended for consistent non-burst workloads.",
                        "why_how_to_fix": (
                            f"AWS Cost Explorer detected steady compute usage over the past 7 days. "
                            f"A 1-year No-Upfront Compute Savings Plan can reduce hourly compute rates by up to 28% without requiring architecture changes."
                        ),
                        "project_tag": "All Projects",
                        "environment_tag": "prod",
                        "source": "Cost Explorer"
                    })
        except Exception as e:
            permissions_log["ce_savings_plans"] = str(e)

    except ClientError as ce:
        code = ce.response.get("Error", {}).get("Code", "")
        permissions_log["ce_recommendations"] = f"denied ({code})"
    except Exception as e:
        permissions_log["ce_recommendations"] = f"error ({str(e)})"

    return recommendations


def scan_ec2_and_other_resources(access_key, secret_key, region, permissions_log):
    """
    Live resource scanner for:
    1. EC2: Idle instances (CloudWatch avg CPU < 10% over 14 days), Stopped instances with EBS
    2. EC2-Other: Unattached EBS volumes, gp2 -> gp3 delta, Snapshots > 90d with no source, Idle NAT Gateways
    3. Elastic IP: Unattached EIPs
    """
    recommendations = []
    ec2 = None
    cw = None

    try:
        ec2 = get_aws_client("ec2", access_key, secret_key, region)
        cw = get_aws_client("cloudwatch", access_key, secret_key, region)
    except Exception as e:
        permissions_log["ec2_client"] = str(e)
        return recommendations

    # --- 1. EC2 Instances (Idle & Stopped with EBS) ---
    try:
        inst_resp = ec2.describe_instances()
        permissions_log["ec2_describe_instances"] = "authorized"

        now = datetime.now(timezone.utc)
        start_time = now - timedelta(days=14)

        for resv in inst_resp.get("Reservations", []):
            for inst in resv.get("Instances", []):
                inst_id = inst.get("InstanceId", "")
                inst_type = inst.get("InstanceType", "")
                state = inst.get("State", {}).get("Name", "")
                tags = extract_resource_tags(inst.get("Tags", []))
                ebs_mappings = [m for m in inst.get("BlockDeviceMappings", []) if "Ebs" in m]

                # Check stopped instances with attached EBS
                if state == "stopped" and ebs_mappings:
                    vol_count = len(ebs_mappings)
                    vol_ids = [m["Ebs"]["VolumeId"] for m in ebs_mappings]
                    # Estimate $10/volume/month average
                    saving = float(vol_count * 10.0)

                    headline = f"Stopped EC2 instance {inst_id} is still paying for {vol_count} attached EBS volume(s)"
                    action = f"Snapshot and terminate stopped instance {inst_id} or detach idle volumes ({', '.join(vol_ids)})"
                    why_how = (
                        f"Instance '{inst_id}' ({inst_type}) is stopped, but its {vol_count} attached EBS volume(s) "
                        f"({', '.join(vol_ids)}) continue to incur storage charges every month.\n\n"
                        f"How to fix:\n"
                        f"1. If this instance is no longer needed, create a final snapshot of its volumes.\n"
                        f"2. Terminate the instance or detach and delete the volumes via the EC2 Console."
                    )

                    recommendations.append({
                        "id": f"ec2-stopped-{inst_id}",
                        "service": "EC2",
                        "resource_id": inst_id,
                        "headline": headline,
                        "action": action,
                        "estimated_monthly_saving": saving,
                        "saving_display": f"~${saving:.2f}/mo",
                        "effort": "low",
                        "risk_note": "Ensure data has been backed up via an AMI or EBS snapshot before terminating.",
                        "why_how_to_fix": why_how,
                        "project_tag": tags["project"],
                        "environment_tag": tags["environment"],
                        "source": "EC2 Scanner"
                    })

                # Check idle running instances via CloudWatch CPUUtilization
                elif state == "running":
                    try:
                        metric_res = cw.get_metric_statistics(
                            Namespace="AWS/EC2",
                            MetricName="CPUUtilization",
                            Dimensions=[{"Name": "InstanceId", "Value": inst_id}],
                            StartTime=start_time,
                            EndTime=now,
                            Period=86400,
                            Statistics=["Average"]
                        )
                        datapoints = metric_res.get("Datapoints", [])
                        if datapoints:
                            avg_cpu = sum(d["Average"] for d in datapoints) / len(datapoints)
                            if avg_cpu < 10.0:
                                # Estimate savings based on baseline instance size
                                saving = 35.0  # standard conservative estimate

                                headline = f"Idle EC2 instance {inst_id} has averaged {avg_cpu:.1f}% CPU (<10%) over the past 14 days"
                                action = f"Stop, schedule, or terminate idle instance {inst_id} ({inst_type})"
                                why_how = (
                                    f"Instance '{inst_id}' ({inst_type}) has shown continuous low utilization ({avg_cpu:.1f}% average CPU) "
                                    f"over the past 14 days.\n\n"
                                    f"How to fix:\n"
                                    f"1. Verify if '{inst_id}' is a dev/test environment that can be scheduled to stop during non-business hours.\n"
                                    f"2. Consider downsizing to a burstable instance type (e.g. t4g) or terminating if no longer active."
                                )

                                recommendations.append({
                                    "id": f"ec2-idle-{inst_id}",
                                    "service": "EC2",
                                    "resource_id": inst_id,
                                    "headline": headline,
                                    "action": action,
                                    "estimated_monthly_saving": saving,
                                    "saving_display": f"~${saving:.2f}/mo",
                                    "effort": "low",
                                    "risk_note": "Verify background cron jobs or periodic workloads before stopping.",
                                    "why_how_to_fix": why_how,
                                    "project_tag": tags["project"],
                                    "environment_tag": tags["environment"],
                                    "source": "CloudWatch Idle Scanner"
                                })
                    except Exception:
                        pass
    except ClientError as ce:
        permissions_log["ec2_describe_instances"] = f"denied ({ce.response.get('Error', {}).get('Code')})"
    except Exception as e:
        permissions_log["ec2_describe_instances"] = f"error ({str(e)})"

    # --- 2. EC2-Other: Unattached EBS Volumes & gp2 to gp3 Delta ---
    all_volume_ids = set()
    try:
        vol_resp = ec2.describe_volumes()
        permissions_log["ec2_describe_volumes"] = "authorized"

        for vol in vol_resp.get("Volumes", []):
            vol_id = vol.get("VolumeId", "")
            all_volume_ids.add(vol_id)
            vol_state = vol.get("State", "")
            vol_type = vol.get("VolumeType", "")
            size_gb = int(vol.get("Size", 0))
            tags = extract_resource_tags(vol.get("Tags", []))

            # Unattached volume check
            if vol_state == "available":
                # Storage rate ~$0.08 - $0.10/GB
                rate = 0.08 if vol_type == "gp3" else 0.10
                saving = round(size_gb * rate, 2)
                if saving < 2.0:
                    saving = 2.0

                headline = f"Unattached EBS volume {vol_id} ({size_gb} GB {vol_type}) is running idle"
                action = f"Delete orphaned EBS volume {vol_id} or take a snapshot before deletion"
                why_how = (
                    f"Volume '{vol_id}' ({size_gb} GB {vol_type}) is not attached to any EC2 instance, "
                    f"incurring continuous storage fees.\n\n"
                    f"How to fix:\n"
                    f"1. Go to EC2 Console → Elastic Block Store → Volumes.\n"
                    f"2. Select '{vol_id}' and confirm it is no longer required.\n"
                    f"3. Actions → Create Snapshot (for archiving), then Actions → Delete Volume."
                )

                recommendations.append({
                    "id": f"ebs-unattached-{vol_id}",
                    "service": "EC2-Other",
                    "resource_id": vol_id,
                    "headline": headline,
                    "action": action,
                    "estimated_monthly_saving": saving,
                    "saving_display": f"~${saving:.2f}/mo",
                    "effort": "low",
                    "risk_note": "Zero downtime. Create a snapshot first if historical data retention is needed.",
                    "why_how_to_fix": why_how,
                    "project_tag": tags["project"],
                    "environment_tag": tags["environment"],
                    "source": "EBS Scanner"
                })

            # gp2 to gp3 migration recommendation
            elif vol_type == "gp2":
                # gp2 is $0.10/GB; gp3 is $0.08/GB -> savings is $0.02/GB (20% saving)
                saving = round(size_gb * 0.02, 2)
                if saving >= 1.0:
                    headline = f"Migrate volume {vol_id} ({size_gb} GB) from gp2 to gp3 to save 20%"
                    action = f"Modify volume {vol_id} type to gp3 with 3,000 baseline IOPS and 125 MB/s throughput"
                    why_how = (
                        f"AWS gp3 volumes cost 20% less per GB than legacy gp2 volumes ($0.08/GB vs. $0.10/GB) "
                        f"while providing higher baseline performance (3,000 IOPS and 125 MB/s included).\n\n"
                        f"How to fix:\n"
                        f"1. In EC2 Console → Volumes → select '{vol_id}'.\n"
                        f"2. Actions → Modify Volume → choose volume type 'gp3'.\n"
                        f"3. Click Modify. Migration happens online with zero downtime."
                    )

                    recommendations.append({
                        "id": f"ebs-gp2-{vol_id}",
                        "service": "EC2-Other",
                        "resource_id": vol_id,
                        "headline": headline,
                        "action": action,
                        "estimated_monthly_saving": saving,
                        "saving_display": f"~${saving:.2f}/mo",
                        "effort": "low",
                        "risk_note": "Zero downtime. AWS Elastic Volumes modifies the volume type live while attached and running.",
                        "why_how_to_fix": why_how,
                        "project_tag": tags["project"],
                        "environment_tag": tags["environment"],
                        "source": "EBS Scanner"
                    })

    except ClientError as ce:
        permissions_log["ec2_describe_volumes"] = f"denied ({ce.response.get('Error', {}).get('Code')})"
    except Exception as e:
        permissions_log["ec2_describe_volumes"] = f"error ({str(e)})"

    # --- 3. EC2-Other: Snapshots > 90 days with no source volume ---
    try:
        snap_resp = ec2.describe_snapshots(OwnerIds=["self"])
        permissions_log["ec2_describe_snapshots"] = "authorized"

        now_dt = datetime.now(timezone.utc)
        ninety_days_ago = now_dt - timedelta(days=90)

        for snap in snap_resp.get("Snapshots", []):
            snap_id = snap.get("SnapshotId", "")
            vol_id = snap.get("VolumeId", "")
            size_gb = int(snap.get("VolumeSize", 0))
            start_time = snap.get("StartTime")
            tags = extract_resource_tags(snap.get("Tags", []))

            if start_time and start_time < ninety_days_ago:
                # If volume is no longer in account
                if vol_id and vol_id not in all_volume_ids:
                    saving = round(size_gb * 0.05, 2)
                    if saving < 1.5:
                        saving = 1.5

                    headline = f"Old snapshot {snap_id} ({size_gb} GB) is >90 days old with deleted source volume"
                    action = f"Archive to AWS Backup Vault or delete obsolete snapshot {snap_id}"
                    why_how = (
                        f"Snapshot '{snap_id}' was created on {start_time.strftime('%Y-%m-%d')} (>90 days ago) "
                        f"from source volume '{vol_id}', which no longer exists in your AWS account.\n\n"
                        f"How to fix:\n"
                        f"1. Open EC2 Console → Elastic Block Store → Snapshots.\n"
                        f"2. Confirm the snapshot is no longer required for compliance or recovery.\n"
                        f"3. Actions → Delete Snapshot."
                    )

                    recommendations.append({
                        "id": f"ebs-snap-{snap_id}",
                        "service": "EC2-Other",
                        "resource_id": snap_id,
                        "headline": headline,
                        "action": action,
                        "estimated_monthly_saving": saving,
                        "saving_display": f"~${saving:.2f}/mo",
                        "effort": "low",
                        "risk_note": "Confirm snapshot is not required for long-term audit/disaster recovery.",
                        "why_how_to_fix": why_how,
                        "project_tag": tags["project"],
                        "environment_tag": tags["environment"],
                        "source": "EBS Snapshot Scanner"
                    })
    except ClientError as ce:
        permissions_log["ec2_describe_snapshots"] = f"denied ({ce.response.get('Error', {}).get('Code')})"
    except Exception as e:
        permissions_log["ec2_describe_snapshots"] = f"error ({str(e)})"

    # --- 4. EC2-Other: Idle NAT Gateways ---
    try:
        nat_resp = ec2.describe_nat_gateways(Filters=[{"Name": "state", "Values": ["available"]}])
        permissions_log["ec2_describe_nat_gateways"] = "authorized"

        for nat in nat_resp.get("NatGateways", []):
            nat_id = nat.get("NatGatewayId", "")
            vpc_id = nat.get("VpcId", "")
            tags = extract_resource_tags(nat.get("Tags", []))

            # NAT Gateways cost $0.045/hour base = $32.85/month
            saving = 32.85
            headline = f"NAT Gateway {nat_id} in {vpc_id} incurs $32.85/month baseline charge"
            action = f"Review traffic on NAT Gateway {nat_id}; consider VPC Gateway Endpoints for S3/DynamoDB"
            why_how = (
                f"NAT Gateway '{nat_id}' incurs a flat $32.85/month fee plus $0.045/GB data processing charges.\n\n"
                f"How to fix:\n"
                f"1. Verify if traffic to S3 or DynamoDB can bypass the NAT Gateway using free AWS VPC Gateway Endpoints.\n"
                f"2. In non-production environments with multiple NAT Gateways, consolidate across subnets."
            )

            recommendations.append({
                "id": f"nat-gw-{nat_id}",
                "service": "EC2-Other",
                "resource_id": nat_id,
                "headline": headline,
                "action": action,
                "estimated_monthly_saving": saving,
                "saving_display": f"~${saving:.2f}/mo",
                "effort": "med",
                "risk_note": "Verify outbound internet access requirements for private subnet workloads before removing.",
                "why_how_to_fix": why_how,
                "project_tag": tags["project"],
                "environment_tag": tags["environment"],
                "source": "NAT Gateway Scanner"
            })
    except ClientError as ce:
        permissions_log["ec2_describe_nat_gateways"] = f"denied ({ce.response.get('Error', {}).get('Code')})"
    except Exception as e:
        permissions_log["ec2_describe_nat_gateways"] = f"error ({str(e)})"

    # --- 5. Elastic IP: Unattached EIPs ---
    try:
        addr_resp = ec2.describe_addresses()
        permissions_log["ec2_describe_addresses"] = "authorized"

        for addr in addr_resp.get("Addresses", []):
            ip = addr.get("PublicIp", "")
            alloc_id = addr.get("AllocationId", ip)
            instance_id = addr.get("InstanceId")
            eni_id = addr.get("NetworkInterfaceId")
            tags = extract_resource_tags(addr.get("Tags", []))

            # If not attached to instance or network interface
            if not instance_id and not eni_id:
                # AWS charges $0.005/hour for unattached IPv4 = ~$3.65/month
                saving = 3.65

                headline = f"Unattached Elastic IP {ip} is incurring idle hourly fees ($3.65/mo)"
                action = f"Release unattached Elastic IP {ip} ({alloc_id})"
                why_how = (
                    f"Elastic IP '{ip}' is not mapped to any running EC2 instance or ENI. "
                    f"AWS bills $0.005/hour ($3.65/month) for every unattached public IPv4 address.\n\n"
                    f"How to fix:\n"
                    f"1. Open EC2 Console → Network & Security → Elastic IPs.\n"
                    f"2. Select '{ip}'.\n"
                    f"3. Actions → Release Elastic IP addresses."
                )

                recommendations.append({
                    "id": f"eip-{alloc_id}",
                    "service": "Elastic IP",
                    "resource_id": ip,
                    "headline": headline,
                    "action": action,
                    "estimated_monthly_saving": saving,
                    "saving_display": f"~${saving:.2f}/mo",
                    "effort": "low",
                    "risk_note": "Zero risk if the IP is truly disused. Once released, the IP returns to AWS pool and cannot be recovered.",
                    "why_how_to_fix": why_how,
                    "project_tag": tags["project"],
                    "environment_tag": tags["environment"],
                    "source": "Elastic IP Scanner"
                })
    except ClientError as ce:
        permissions_log["ec2_describe_addresses"] = f"denied ({ce.response.get('Error', {}).get('Code')})"
    except Exception as e:
        permissions_log["ec2_describe_addresses"] = f"error ({str(e)})"

    return recommendations


def scan_s3_resources(access_key, secret_key, region, permissions_log):
    """
    Live resource scanner for S3:
    1. Buckets with no lifecycle policy -> suggest transition to IA/Glacier
    2. Incomplete multipart uploads
    3. Old non-current object versions when versioning is on
    """
    recommendations = []
    try:
        s3 = get_aws_client("s3", access_key, secret_key, region)
        buckets_resp = s3.list_buckets()
        permissions_log["s3_list_buckets"] = "authorized"

        for b in buckets_resp.get("Buckets", [])[:20]:
            b_name = b.get("Name", "")

            # Tags
            tags = {"project": "Untagged", "environment": "unknown"}
            try:
                tag_resp = s3.get_bucket_tagging(Bucket=b_name)
                tags = extract_resource_tags(tag_resp.get("TagSet", []))
            except Exception:
                pass

            # 1. Lifecycle check
            has_lifecycle = False
            has_incomplete_cleanup = False
            has_noncurrent_expiry = False

            try:
                lc_resp = s3.get_bucket_lifecycle_configuration(Bucket=b_name)
                rules = lc_resp.get("Rules", [])
                for r in rules:
                    if r.get("Status") == "Enabled":
                        if r.get("Transitions"):
                            has_lifecycle = True
                        if r.get("AbortIncompleteMultipartUpload"):
                            has_incomplete_cleanup = True
                        if r.get("NoncurrentVersionExpiration"):
                            has_noncurrent_expiry = True
            except ClientError as ce:
                # NoSuchLifecycleConfiguration is expected when no lifecycle exists
                pass

            # If no lifecycle policy
            if not has_lifecycle:
                saving = 18.0  # Conservative estimate
                headline = f"S3 bucket '{b_name}' has no lifecycle transition rules configured"
                action = f"Add S3 Lifecycle policy on '{b_name}' to transition older objects to S3 Standard-IA or Glacier"
                why_how = (
                    f"Bucket '{b_name}' stores all objects in S3 Standard indefinitely ($0.023/GB). "
                    f"Objects rarely accessed after 30–90 days can be automatically transitioned to S3 Standard-IA ($0.0125/GB) "
                    f"or Glacier Instant Retrieval ($0.004/GB) for up to 60–80% savings.\n\n"
                    f"How to fix:\n"
                    f"1. Open S3 Console → Buckets → '{b_name}' → Management tab.\n"
                    f"2. Create lifecycle rule → apply to all objects.\n"
                    f"3. Add transition to Standard-IA after 30 days and Glacier Flexible Archive after 90 days."
                )

                recommendations.append({
                    "id": f"s3-lifecycle-{b_name}",
                    "service": "S3",
                    "resource_id": b_name,
                    "headline": headline,
                    "action": action,
                    "estimated_monthly_saving": saving,
                    "saving_display": f"~${saving:.2f}/mo",
                    "effort": "low",
                    "risk_note": "Standard-IA objects have a 30-day minimum storage charge and retrieval fees if accessed frequently.",
                    "why_how_to_fix": why_how,
                    "project_tag": tags["project"],
                    "environment_tag": tags["environment"],
                    "source": "S3 Scanner"
                })

            # 2. Incomplete multipart uploads check
            if not has_incomplete_cleanup:
                try:
                    mp_resp = s3.list_multipart_uploads(Bucket=b_name, MaxUploads=5)
                    uploads = mp_resp.get("Uploads", [])
                    if uploads:
                        saving = 8.0
                        headline = f"Bucket '{b_name}' contains unfinished multipart uploads incurring storage fees"
                        action = f"Enable rule to automatically abort incomplete multipart uploads after 7 days on '{b_name}'"
                        why_how = (
                            f"Unfinished multipart uploads in bucket '{b_name}' permanently occupy storage space "
                            f"until aborted or completed.\n\n"
                            f"How to fix:\n"
                            f"1. In S3 Management → Lifecycle rules for '{b_name}'.\n"
                            f"2. Check 'Delete expired object delete markers or incomplete multipart uploads'.\n"
                            f"3. Set incomplete multipart upload abort duration to 7 days."
                        )

                        recommendations.append({
                            "id": f"s3-mp-{b_name}",
                            "service": "S3",
                            "resource_id": b_name,
                            "headline": headline,
                            "action": action,
                            "estimated_monthly_saving": saving,
                            "saving_display": f"~${saving:.2f}/mo",
                            "effort": "low",
                            "risk_note": "Zero risk to valid uploaded objects. Only removes abandoned upload fragments.",
                            "why_how_to_fix": why_how,
                            "project_tag": tags["project"],
                            "environment_tag": tags["environment"],
                            "source": "S3 Scanner"
                        })
                except Exception:
                    pass

            # 3. Noncurrent version expiration check
            try:
                v_resp = s3.get_bucket_versioning(Bucket=b_name)
                if v_resp.get("Status") == "Enabled" and not has_noncurrent_expiry:
                    saving = 12.0
                    headline = f"Versioned bucket '{b_name}' has no policy to expire old noncurrent object versions"
                    action = f"Add lifecycle rule to expire noncurrent versions after 30–60 days on '{b_name}'"
                    why_how = (
                        f"Versioning is enabled on '{b_name}', so overwritten or deleted objects are retained indefinitely "
                        f"as noncurrent versions, accumulating hidden storage costs.\n\n"
                        f"How to fix:\n"
                        f"1. In S3 Management → Lifecycle rules for '{b_name}'.\n"
                        f"2. Add rule with action 'Permanently delete noncurrent versions of objects'.\n"
                        f"3. Specify retention period (e.g. 30 or 60 days)."
                    )

                    recommendations.append({
                        "id": f"s3-versions-{b_name}",
                        "service": "S3",
                        "resource_id": b_name,
                        "headline": headline,
                        "action": action,
                        "estimated_monthly_saving": saving,
                        "saving_display": f"~${saving:.2f}/mo",
                        "effort": "low",
                        "risk_note": "Verify regulatory audit requirements before expiring historical versions.",
                        "why_how_to_fix": why_how,
                        "project_tag": tags["project"],
                        "environment_tag": tags["environment"],
                        "source": "S3 Scanner"
                    })
            except Exception:
                pass

    except ClientError as ce:
        permissions_log["s3_list_buckets"] = f"denied ({ce.response.get('Error', {}).get('Code')})"
    except Exception as e:
        permissions_log["s3_list_buckets"] = f"error ({str(e)})"

    return recommendations


def fetch_cost_explorer_backbone(access_key, secret_key, region, permissions_log):
    """
    Fetch Cost Explorer backbone data:
    - Current month spend
    - Previous month spend & trend %
    - Forecast
    - Historical monthly usage
    - Cost Anomaly Detection findings
    """
    today = date.today()
    ranges = compute_month_ranges(today)
    all_months = ranges["all_months"]
    historical_months = ranges["historical_months"]
    current_month_info = ranges["current_month"]
    total_start = ranges["total_start"]
    total_end = ranges["total_end"]
    days_elapsed = ranges["days_elapsed"]
    days_in_current_month = ranges["days_in_current_month"]

    client = get_aws_client("ce", access_key, secret_key, region)

    # 1. Historical monthly spend
    month_keys = [m["key"] for m in all_months]
    month_labels = [m["label"] for m in all_months]
    hist_keys = [m["key"] for m in historical_months]
    curr_key = current_month_info["key"]

    services_dict = {}
    total_monthly_spend = {m_key: 0.0 for m_key in month_keys}

    try:
        ce_res = client.get_cost_and_usage(
            TimePeriod={"Start": total_start.strftime("%Y-%m-%d"), "End": total_end.strftime("%Y-%m-%d")},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}]
        )
        permissions_log["ce_get_cost_and_usage"] = "authorized"

        for period in ce_res.get("ResultsByTime", []):
            start_str = period.get("TimePeriod", {}).get("Start", "")
            p_key = start_str[:7]

            for group in period.get("Groups", []):
                service_name = group["Keys"][0]
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                if service_name not in services_dict:
                    services_dict[service_name] = {mk: 0.0 for mk in month_keys}
                services_dict[service_name][p_key] = round(amount, 2)
                if p_key in total_monthly_spend:
                    total_monthly_spend[p_key] += amount
    except ClientError as ce:
        permissions_log["ce_get_cost_and_usage"] = f"denied ({ce.response.get('Error', {}).get('Code')})"
    except Exception as e:
        permissions_log["ce_get_cost_and_usage"] = f"error ({str(e)})"

    for k in total_monthly_spend:
        total_monthly_spend[k] = round(total_monthly_spend[k], 2)

    total_current_cost = total_monthly_spend.get(curr_key, 0.0)
    total_daily_avg = total_current_cost / max(1, days_elapsed)
    dashboard_estimated_month_end = round(total_daily_avg * days_in_current_month, 2)

    hist_spends = [total_monthly_spend.get(hk, 0.0) for hk in hist_keys]
    total_hist_avg = round(sum(hist_spends) / max(1, len(hist_keys)), 2)
    prev_month_spend = hist_spends[-1] if hist_spends else 0.0

    # Trend vs last month
    if prev_month_spend > 0:
        trend_vs_last_month_pct = round(((total_current_cost - prev_month_spend) / prev_month_spend) * 100, 1)
    else:
        trend_vs_last_month_pct = 0.0

    # Trend vs 3-month average
    if total_hist_avg > 0:
        trend_vs_avg_pct = round(((dashboard_estimated_month_end - total_hist_avg) / total_hist_avg) * 100, 1)
    else:
        trend_vs_avg_pct = 0.0

    # 2. Native AWS Forecast
    aws_forecast = None
    forecast_status = "Forecast data is currently unavailable."
    try:
        tomorrow = today + timedelta(days=1)
        next_month_start = date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)
        if tomorrow < next_month_start:
            fc_res = client.get_cost_forecast(
                TimePeriod={"Start": tomorrow.strftime("%Y-%m-%d"), "End": next_month_start.strftime("%Y-%m-%d")},
                Metric="UNBLENDED_COST",
                Granularity="MONTHLY"
            )
            amt = fc_res.get("Total", {}).get("Amount")
            if amt is not None:
                aws_forecast = round(float(amt), 2)
                forecast_status = "Available"
                permissions_log["ce_get_cost_forecast"] = "authorized"
    except ClientError as ce:
        err_code = ce.response.get("Error", {}).get("Code", "")
        permissions_log["ce_get_cost_forecast"] = f"denied ({err_code})"
        if err_code == "AccessDeniedException":
            forecast_status = "Requires ce:GetCostForecast IAM permission."
        else:
            forecast_status = f"Forecast unavailable ({err_code})."
    except Exception as e:
        permissions_log["ce_get_cost_forecast"] = str(e)

    # 3. Cost Anomaly Detection
    anomalies = []
    try:
        thirty_days_ago = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        today_str = today.strftime("%Y-%m-%d")
        anom_res = client.get_anomalies(DateInterval={"StartDate": thirty_days_ago, "EndDate": today_str})
        permissions_log["ce_get_anomalies"] = "authorized"
        for a in anom_res.get("Anomalies", []):
            anom_score = a.get("AnomalyScore", {}).get("CurrentScore", 0.0)
            impact = a.get("Impact", {}).get("TotalImpact", 0.0)
            dim_val = a.get("DimensionValue", "AWS Service")
            anomalies.append({
                "service": dim_val,
                "score": anom_score,
                "impact": round(float(impact), 2),
                "start_date": a.get("AnomalyStartDate", ""),
                "end_date": a.get("AnomalyEndDate", "")
            })
    except ClientError as ce:
        err_code = ce.response.get("Error", {}).get("Code", "")
        permissions_log["ce_get_anomalies"] = f"denied ({err_code})"
    except Exception as e:
        permissions_log["ce_get_anomalies"] = str(e)

    return {
        "current_month_cost": total_current_cost,
        "prev_month_cost": prev_month_spend,
        "trend_vs_last_month_pct": trend_vs_last_month_pct,
        "trend_vs_avg_pct": trend_vs_avg_pct,
        "previous_3_month_avg": total_hist_avg,
        "dashboard_estimated_month_end": dashboard_estimated_month_end,
        "aws_cost_forecast": aws_forecast,
        "forecast_status": forecast_status,
        "anomalies": anomalies,
        "month_labels": month_labels,
        "total_trend": [total_monthly_spend.get(mk, 0.0) for mk in month_keys],
        "services_breakdown": services_dict,
        "days_elapsed": days_elapsed,
        "days_in_month": days_in_current_month
    }


def generate_fallback_suggestions_from_billing(billing_backbone):
    """
    When live resource describe calls or Compute Optimizer are not authorized,
    derive high-value, actionable recommendations directly from real Cost Explorer spend.
    Ensures the user always receives actionable, plain-language guidance with project tags.
    """
    fallback_recs = []
    services = billing_backbone.get("services_breakdown", {})
    curr_month_key = list(services.values())[0].keys() if services else []
    last_key = sorted(curr_month_key)[-1] if curr_month_key else ""

    # Sort services by spend
    sorted_services = []
    for s_name, m_costs in services.items():
        cost = m_costs.get(last_key, 0.0)
        sorted_services.append((s_name, cost))
    sorted_services.sort(key=lambda x: x[1], reverse=True)

    ec2_spend = sum(cost for s, cost in sorted_services if "compute" in s.lower() or "elastic compute cloud" in s.lower())
    ec2_other_spend = sum(cost for s, cost in sorted_services if "ec2 - other" in s.lower())
    s3_spend = sum(cost for s, cost in sorted_services if "simple storage" in s.lower() or "s3" in s.lower())

    # 1. EC2 Compute Rightsizing
    if ec2_spend > 0:
        sav = round(ec2_spend * 0.25, 2)
        fallback_recs.append({
            "id": "sug-ec2-rightsize-fallback",
            "service": "EC2",
            "resource_id": "All Running EC2 Instances",
            "headline": "Right-size over-provisioned EC2 instances to reduce monthly compute spend",
            "action": "Review CPU and memory utilization in CloudWatch; downsize underutilized instances by one tier",
            "estimated_monthly_saving": max(35.0, sav),
            "saving_display": f"~${max(35.0, sav):.2f}/mo",
            "effort": "low",
            "risk_note": "Requires brief instance reboot. Ensure memory usage is under 70% before downsizing.",
            "why_how_to_fix": (
                f"EC2 compute spending is running at ${ec2_spend:.2f}/month. "
                f"Right-sizing instances with average CPU < 15% to smaller sizes or modern graviton (arm64) types "
                f"typically yields 15%–30% monthly savings.\n\n"
                f"How to fix:\n"
                f"1. Open EC2 Console → Instances.\n"
                f"2. Sort by CPU utilization in CloudWatch metrics.\n"
                f"3. Enable AWS Compute Optimizer in your account to receive instance-level recommendations."
            ),
            "project_tag": "Production",
            "environment_tag": "prod",
            "source": "Cost Explorer Pattern Analysis"
        })

    # 2. EC2-Other (EBS gp2 to gp3 & Unattached Volumes)
    if ec2_other_spend > 0:
        sav = round(ec2_other_spend * 0.20, 2)
        fallback_recs.append({
            "id": "sug-ebs-gp3-fallback",
            "service": "EC2-Other",
            "resource_id": "gp2 EBS Storage Volumes",
            "headline": "Upgrade older gp2 EBS storage volumes to gp3 for an immediate 20% cost reduction",
            "action": "Modify volume types from gp2 to gp3 in the EC2 Console with zero downtime",
            "estimated_monthly_saving": max(20.0, sav),
            "saving_display": f"~${max(20.0, sav):.2f}/mo",
            "effort": "low",
            "risk_note": "Zero downtime. AWS Elastic Volumes migrates storage live in the background without rebooting.",
            "why_how_to_fix": (
                f"EC2-Other storage and transfer spend is running at ${ec2_other_spend:.2f}/month. "
                f"Upgrading gp2 volumes to gp3 reduces storage costs by 20% while boosting baseline throughput to 125 MB/s and 3,000 IOPS.\n\n"
                f"How to fix:\n"
                f"1. Open EC2 Console → Volumes.\n"
                f"2. Filter by Volume Type: 'gp2'.\n"
                f"3. Actions → Modify Volume → change to 'gp3' and save."
            ),
            "project_tag": "Infrastructure",
            "environment_tag": "prod",
            "source": "Cost Explorer Pattern Analysis"
        })

        fallback_recs.append({
            "id": "sug-ebs-unattached-fallback",
            "service": "EC2-Other",
            "resource_id": "Unattached EBS Volumes",
            "headline": "Audit and delete unattached EBS volumes left behind by terminated instances",
            "action": "Find volumes with state 'Available' and delete them after taking an optional backup snapshot",
            "estimated_monthly_saving": 15.0,
            "saving_display": "~$15.00/mo",
            "effort": "low",
            "risk_note": "Zero downtime. Take an EBS snapshot before deleting if historical data might be required.",
            "why_how_to_fix": (
                "When EC2 instances are terminated without the 'Delete on Termination' flag, their attached EBS volumes "
                "remain active in 'available' state and continue incurring storage fees indefinitely."
            ),
            "project_tag": "Infrastructure",
            "environment_tag": "prod",
            "source": "Cost Explorer Pattern Analysis"
        })

    # 3. S3 Lifecycle Transition
    if s3_spend > 0:
        sav = round(s3_spend * 0.35, 2)
        fallback_recs.append({
            "id": "sug-s3-lifecycle-fallback",
            "service": "S3",
            "resource_id": "All S3 Storage Buckets",
            "headline": "Transition infrequently accessed S3 objects to S3 Standard-IA or Glacier",
            "action": "Configure S3 Lifecycle policies to automatically move objects older than 30 days to Standard-IA",
            "estimated_monthly_saving": max(12.0, sav),
            "saving_display": f"~${max(12.0, sav):.2f}/mo",
            "effort": "low",
            "risk_note": "Standard-IA objects have a 30-day minimum storage period and small retrieval charges.",
            "why_how_to_fix": (
                f"S3 spending is running at ${s3_spend:.2f}/month. "
                f"Transitioning aging objects to Infrequent Access ($0.0125/GB) saves 45% over S3 Standard ($0.023/GB).\n\n"
                f"How to fix:\n"
                f"1. Open S3 Console → select your largest bucket.\n"
                f"2. Management tab → Create lifecycle rule.\n"
                f"3. Enable transition to Standard-IA after 30 days."
            ),
            "project_tag": "Storage",
            "environment_tag": "prod",
            "source": "Cost Explorer Pattern Analysis"
        })

    # 4. Elastic IP audit
    fallback_recs.append({
        "id": "sug-eip-release-fallback",
        "service": "Elastic IP",
        "resource_id": "Unattached Public IPv4 Addresses",
        "headline": "Release idle Elastic IP addresses not attached to running instances",
        "action": "Release unassociated Elastic IPs in the EC2 Console to eliminate idle IPv4 charges",
        "estimated_monthly_saving": 7.30,
        "saving_display": "~$7.30/mo",
        "effort": "low",
        "risk_note": "Zero risk if the IP is not in active DNS records. Released IPs return to the AWS public pool.",
        "why_how_to_fix": (
            "AWS charges $0.005/hour ($3.65/month per IP) for all unattached public IPv4 addresses.\n\n"
            "How to fix:\n"
            "1. In EC2 Console → Elastic IPs.\n"
            "2. Identify addresses without an associated instance ID.\n"
            "3. Actions → Release Elastic IP addresses."
        ),
        "project_tag": "Networking",
        "environment_tag": "prod",
        "source": "Cost Explorer Pattern Analysis"
    })

    return fallback_recs


# =========================================================================
# MAIN CONSOLIDATION PIPELINE
# =========================================================================

def analyze_cost_optimizer(access_key, secret_key, region="us-east-1", account_id="default", bypass_cache=False):
    """
    Main Cost Optimizer Pipeline:
    1. Checks local cache (24h TTL) unless bypass_cache is requested.
    2. Fetches Cost Explorer backbone data (current spend, trend, forecast, anomalies).
    3. Scans Cost Optimization Hub recommendations.
    4. Scans Compute Optimizer recommendations.
    5. Scans Cost Explorer native recommendations.
    6. Scans live EC2, EC2-Other, S3, and Elastic IP resources.
    7. Groups suggestions by Service & attributes to Project/Environment tags.
    8. Ranks suggestions by estimated monthly savings descending.
    9. Caches results and returns clean structured output.
    """
    if not bypass_cache:
        cached = get_cached_optimizer_data(account_id)
        if cached:
            cached["from_cache"] = True
            return cached

    permissions_log = {}

    # 1. Cost Explorer Backbone (Current Month, Trend, Forecast, Anomalies)
    backbone = fetch_cost_explorer_backbone(access_key, secret_key, region, permissions_log)

    all_suggestions = []

    # 2. Priority 1: Cost Optimization Hub
    coh_recs = scan_cost_optimization_hub(access_key, secret_key, region, permissions_log)
    all_suggestions.extend(coh_recs)

    # 3. Priority 2: Compute Optimizer
    co_recs = scan_compute_optimizer(access_key, secret_key, region, permissions_log)
    all_suggestions.extend(co_recs)

    # 4. Priority 3: Cost Explorer Rightsizing & Savings Plans
    ce_recs = scan_cost_explorer_recommendations(access_key, secret_key, region, permissions_log)
    all_suggestions.extend(ce_recs)

    # 5. Priority 4: Live Resource Scanners (EC2, EC2-Other, S3, Elastic IP)
    ec2_other_recs = scan_ec2_and_other_resources(access_key, secret_key, region, permissions_log)
    all_suggestions.extend(ec2_other_recs)

    s3_recs = scan_s3_resources(access_key, secret_key, region, permissions_log)
    all_suggestions.extend(s3_recs)

    # 6. Fallback if live resource calls were unauthorized/empty
    if not all_suggestions:
        fallback_recs = generate_fallback_suggestions_from_billing(backbone)
        all_suggestions.extend(fallback_recs)

    # Deduplicate suggestions by resource_id & service
    seen_keys = set()
    deduped_suggestions = []
    for s in all_suggestions:
        key = f"{s['service']}-{s['resource_id']}-{s['headline'][:20]}"
        if key not in seen_keys:
            seen_keys.add(key)
            deduped_suggestions.append(s)

    # Rank by estimated monthly saving descending
    deduped_suggestions.sort(key=lambda x: x["estimated_monthly_saving"], reverse=True)

    # Calculate summary metrics
    total_savings = round(sum(s["estimated_monthly_saving"] for s in deduped_suggestions), 2)
    suggestions_count = len(deduped_suggestions)
    biggest_single_saving = deduped_suggestions[0] if deduped_suggestions else None

    # Collect unique projects for filtering
    projects_set = set()
    for s in deduped_suggestions:
        p = s.get("project_tag", "Untagged")
        if p:
            projects_set.add(p)
    projects_list = ["All Projects"] + sorted(list(projects_set))

    # Service breakdown counts
    service_groups = {
        "EC2": [s for s in deduped_suggestions if s["service"] == "EC2"],
        "EC2-Other": [s for s in deduped_suggestions if s["service"] == "EC2-Other"],
        "S3": [s for s in deduped_suggestions if s["service"] == "S3"],
        "Elastic IP": [s for s in deduped_suggestions if s["service"] == "Elastic IP"]
    }

    last_updated_str = datetime.now().strftime("%d %b %Y, %I:%M %p")

    result = {
        "success": True,
        "from_cache": False,
        "last_updated": last_updated_str,
        "summary": {
            "total_estimated_monthly_savings": total_savings,
            "total_estimated_monthly_savings_display": f"~${total_savings:.2f}/mo",
            "total_suggestions_count": suggestions_count,
            "biggest_single_saving": {
                "headline": biggest_single_saving["headline"] if biggest_single_saving else "None detected",
                "service": biggest_single_saving["service"] if biggest_single_saving else "",
                "resource_id": biggest_single_saving["resource_id"] if biggest_single_saving else "",
                "saving_display": biggest_single_saving["saving_display"] if biggest_single_saving else "$0.00/mo",
                "saving_amount": biggest_single_saving["estimated_monthly_saving"] if biggest_single_saving else 0.0
            } if biggest_single_saving else None,
            "current_month_cost": backbone["current_month_cost"],
            "prev_month_cost": backbone["prev_month_cost"],
            "trend_vs_last_month_pct": backbone["trend_vs_last_month_pct"],
            "dashboard_estimated_month_end": backbone["dashboard_estimated_month_end"],
            "aws_cost_forecast": backbone["aws_cost_forecast"],
            "forecast_status": backbone["forecast_status"]
        },
        "suggestions": deduped_suggestions,
        "service_groups": {
            "EC2": {
                "count": len(service_groups["EC2"]),
                "total_savings": round(sum(s["estimated_monthly_saving"] for s in service_groups["EC2"]), 2)
            },
            "EC2-Other": {
                "count": len(service_groups["EC2-Other"]),
                "total_savings": round(sum(s["estimated_monthly_saving"] for s in service_groups["EC2-Other"]), 2)
            },
            "S3": {
                "count": len(service_groups["S3"]),
                "total_savings": round(sum(s["estimated_monthly_saving"] for s in service_groups["S3"]), 2)
            },
            "Elastic IP": {
                "count": len(service_groups["Elastic IP"]),
                "total_savings": round(sum(s["estimated_monthly_saving"] for s in service_groups["Elastic IP"]), 2)
            }
        },
        "projects_list": projects_list,
        "anomalies": backbone["anomalies"],
        "permissions_status": permissions_log,
        "chart_data": {
            "months": backbone["month_labels"],
            "total_trend": backbone["total_trend"]
        }
    }

    set_cached_optimizer_data(account_id, result)
    return result
